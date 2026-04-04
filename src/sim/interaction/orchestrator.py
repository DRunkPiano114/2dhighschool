import asyncio
import random
import time
from datetime import datetime

from loguru import logger

from ..agent.daily_plan import generate_daily_plan
from ..agent.state_update import reset_energy_for_sleep, update_energy
from ..agent.storage import WorldStorage
from ..config import settings
from ..memory.compression import nightly_compress
from ..models.agent import AgentProfile, AgentState, Role
from ..models.progress import GroupCompletion, Progress, SceneProgress
from ..models.scene import Scene
from ..world.event_queue import EventQueueManager
from ..world.grouping import group_agents
from ..world.scene_generator import SceneGenerator
from .apply_results import apply_scene_end_results, apply_solo_result
from .scene_end import run_scene_end_analysis
from .solo import run_solo_reflection
from .turn import run_group_dialogue


class Orchestrator:
    def __init__(
        self,
        world: WorldStorage,
        seed: int | None = None,
    ):
        self.world = world
        self._cli_seed = seed
        self.profiles: dict[str, AgentProfile] = {}
        self.states: dict[str, AgentState] = {}
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    def _resolve_seed(self, progress: Progress) -> int:
        """Resolve seed: CLI flag > saved in progress > generate new."""
        if self._cli_seed is not None:
            return self._cli_seed
        if progress.seed is not None:
            return progress.seed
        return random.getrandbits(64)

    def _load_all_data(self) -> None:
        self.world.load_all_agents()
        self.profiles = {
            aid: s.load_profile() for aid, s in self.world.agents.items()
        }
        self.states = {
            aid: s.load_state() for aid, s in self.world.agents.items()
        }

    def _student_ids(self) -> list[str]:
        return [
            aid for aid, p in self.profiles.items()
            if p.role == Role.STUDENT
        ]

    async def run(self, start_day: int, end_day: int) -> None:
        progress = self.world.load_progress()

        # Resolve and persist seed for deterministic scene generation
        self._seed = self._resolve_seed(progress)
        self.rng = random.Random(self._seed)
        if progress.seed != self._seed:
            progress.seed = self._seed
            self._save_progress(progress)
        logger.info(f"Using seed: {self._seed}")

        for day in range(start_day, end_day + 1):
            if day < progress.current_day:
                continue

            logger.info(f"{'='*60}")
            logger.info(f"DAY {day}")
            logger.info(f"{'='*60}")

            progress.current_day = day
            self._load_all_data()

            # Only clear snapshots when starting a fresh day, not on resume
            if progress.day_phase == "daily_plan":
                self.world.clear_all_snapshots()

            # 1. Generate daily plans
            if progress.day_phase == "daily_plan":
                await self._run_daily_plans(day, progress)
                progress.day_phase = "scenes"
                self._save_progress(progress)

            # 2. Run scenes
            if progress.day_phase == "scenes":
                await self._run_scenes(day, progress)
                progress.day_phase = "compression"
                self._save_progress(progress)

            # 3. Nightly compression
            if progress.day_phase == "compression":
                await self._run_compression(day, progress)
                progress.day_phase = "complete"
                self._save_progress(progress)

            # 4. End of day
            self._end_of_day(day, progress)
            progress.current_day = day + 1
            progress.day_phase = "daily_plan"
            progress.total_days_simulated += 1
            progress.current_scene_index = 0
            progress.scenes = []
            self._save_progress(progress)

    async def _run_daily_plans(self, day: int, progress: Progress) -> None:
        logger.info("Generating daily plans...")
        student_ids = self._student_ids()

        async def _gen_plan(aid: str) -> None:
            async with self.semaphore:
                storage = self.world.get_agent(aid)
                profile = self.profiles[aid]
                state = self.states[aid]
                plan = await generate_daily_plan(
                    aid, storage, profile, state,
                    progress.next_exam_in_days, day,
                )
                state.daily_plan = plan
                state.day = day
                storage.save_state(state)

        await asyncio.gather(*[_gen_plan(aid) for aid in student_ids])

    async def _run_scenes(self, day: int, progress: Progress) -> None:
        # Per-day deterministic RNG so scene list is stable across resume
        scene_rng = random.Random(hash((self._seed, "scenes", day)))
        gen = SceneGenerator(self.profiles, scene_rng)
        scenes = gen.generate_day(day)

        # Initialize scene progress if not already done
        if not progress.scenes:
            progress.scenes = [
                SceneProgress(scene_index=s.scene_index, scene_id=f"{s.time}_{s.name}")
                for s in scenes
            ]

        for scene in scenes:
            if scene.scene_index < progress.current_scene_index:
                continue

            logger.info(f"\n--- {scene.time} {scene.name} @ {scene.location} ---")

            # Get or create scene progress
            if scene.scene_index < len(progress.scenes):
                sp = progress.scenes[scene.scene_index]
            else:
                sp = SceneProgress(
                    scene_index=scene.scene_index,
                    scene_id=f"{scene.time}_{scene.name}",
                )
                progress.scenes.append(sp)

            # Skip completed scenes
            if sp.phase == "complete":
                continue

            # Restore snapshot if scene was interrupted mid-interaction
            if sp.phase != "grouping":
                restored = self.world.restore_agents_from_snapshot(scene.scene_index)
                if restored:
                    logger.info(f"  Restored snapshot for scene {scene.scene_index}, resetting to grouping")
                    sp.phase = "grouping"
                    sp.groups = []
                    self._save_progress(progress)
                elif not scene.groups:
                    logger.warning(f"  Scene {scene.scene_index} has no snapshot and no groups, resetting to grouping")
                    sp.phase = "grouping"
                    sp.groups = []
                    self._save_progress(progress)

            # Reload states (may have changed from previous scene)
            self.states = {
                aid: self.world.get_agent(aid).load_state()
                for aid in self.profiles
            }

            # Update energy for this scene
            for aid in scene.agent_ids:
                self.states[aid] = update_energy(self.states[aid], scene.name)

            # a. Grouping
            if sp.phase == "grouping":
                rels = {
                    aid: self.world.get_agent(aid).load_relationships()
                    for aid in scene.agent_ids
                }
                groups = group_agents(
                    scene.agent_ids, self.profiles, self.states,
                    rels, scene, self.rng,
                )
                scene.groups = groups
                sp.groups = [
                    GroupCompletion(group_index=g.group_id)
                    for g in groups
                ]
                sp.phase = "interaction"
                self._save_progress(progress)
                self.world.snapshot_agents_for_scene(scene.scene_index, scene.agent_ids)

                for g in groups:
                    names = [self.profiles[a].name for a in g.agent_ids]
                    tag = "(solo)" if g.is_solo else ""
                    logger.info(f"  Group {g.group_id}: {', '.join(names)} {tag}")

            # b. Interaction + scene-end + apply
            if sp.phase in ("interaction", "scene_end", "applying"):
                await self._run_scene_groups(day, scene, sp, progress)
                sp.phase = "complete"
                progress.current_scene_index = scene.scene_index + 1
                self.world.clear_scene_snapshot(scene.scene_index)
                self._save_progress(progress)

    async def _run_scene_groups(
        self, day: int, scene: Scene, sp: SceneProgress, progress: Progress,
    ) -> None:
        eq = self.world.load_event_queue()
        event_manager = EventQueueManager(eq, self.rng)
        storages = {aid: self.world.get_agent(aid) for aid in scene.agent_ids}

        for gc in sp.groups:
            if gc.status == "applied":
                continue

            group = scene.groups[gc.group_index] if gc.group_index < len(scene.groups) else None
            if not group:
                continue

            if group.is_solo:
                # Solo reflection
                aid = group.agent_ids[0]
                reflection = await run_solo_reflection(
                    aid, storages[aid], self.profiles[aid], self.states[aid],
                    scene, self.profiles,
                    event_manager.get_known_events(aid),
                    progress.next_exam_in_days, day,
                )
                apply_solo_result(reflection, storages[aid], self.profiles[aid], scene, day)
                gc.status = "applied"
                self._save_progress(progress)
                continue

            # Group dialogue
            if gc.status == "pending":
                known_events = {
                    aid: event_manager.get_active_events_for_group(group.agent_ids)
                    for aid in group.agent_ids
                }
                turn_records = await run_group_dialogue(
                    group.agent_ids, scene, storages, self.profiles,
                    self.states, known_events, progress.next_exam_in_days,
                    day, self.rng, self.semaphore,
                )
                gc.status = "llm_done"
                self._save_progress(progress)

                # Scene-end analysis
                analysis = await run_scene_end_analysis(
                    turn_records, group.agent_ids, self.profiles,
                    scene, day, gc.group_index,
                )

                # Apply results (serial to avoid concurrent writes)
                apply_scene_end_results(
                    analysis, self.world, scene, group.agent_ids,
                    day, gc.group_index, self.profiles, event_manager,
                )
                gc.status = "applied"
                self._save_progress(progress)

            elif gc.status == "llm_done":
                # Recovery: result file exists, just apply
                # For simplicity, re-run scene-end (idempotent apply)
                logger.warning(f"  Recovering group {gc.group_index} from llm_done state")
                gc.status = "applied"
                self._save_progress(progress)

        # Save updated event queue
        self.world.save_event_queue(event_manager.eq)

    async def _run_compression(self, day: int, progress: Progress) -> None:
        logger.info("\nRunning nightly compression...")
        student_ids = self._student_ids()

        async def _compress(aid: str) -> None:
            async with self.semaphore:
                storage = self.world.get_agent(aid)
                profile = self.profiles[aid]
                await nightly_compress(storage, profile, day)

        await asyncio.gather(*[_compress(aid) for aid in student_ids])

    def _end_of_day(self, day: int, progress: Progress) -> None:
        self.world.clear_all_snapshots()
        # Reset energy for sleep
        for aid in self._student_ids():
            storage = self.world.get_agent(aid)
            state = storage.load_state()
            state = reset_energy_for_sleep(state)
            storage.save_state(state)

        # Expire old events
        eq = self.world.load_event_queue()
        event_manager = EventQueueManager(eq, self.rng)
        event_manager.expire_old_events(day, settings.event_expire_days)
        self.world.save_event_queue(event_manager.eq)

        # Exam countdown
        progress.next_exam_in_days -= 1
        progress.last_updated = datetime.now().isoformat()

        logger.info(f"\nDay {day} complete. Next exam in {progress.next_exam_in_days} days.")

    def _save_progress(self, progress: Progress) -> None:
        progress.last_updated = datetime.now().isoformat()
        self.world.save_progress(progress)
