"""Time-travel context assembly for chat modes.

Reconstructs an agent's full state at a specific (day, time_period) point,
loading from daily snapshots rather than the live agent files.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from ..agent.context import _profile_summary
from ..agent.qualitative import energy_label, intensity_label, pressure_label, relationship_label
from ..agent.self_narrative import SelfNarrativeResult
from ..agent.storage import AgentStorage, WorldStorage
from ..config import settings
from ..models.agent import AgentProfile, AgentState, Emotion, Role
from ..models.memory import KeyMemoryFile
from ..models.relationship import RelationshipFile

# Time period ordering for "today so far" filtering
TIME_PERIOD_ORDER = ["08:45", "12:00", "15:30", "22:00"]


def _snapshot_dir(day: int) -> Path:
    """Return path to logs/day_{N}/agent_snapshots/."""
    return settings.logs_dir / f"day_{day:03d}" / "agent_snapshots"


def _load_snapshot_state(agent_id: str, day: int) -> AgentState | None:
    """Load agent state from a daily snapshot."""
    path = _snapshot_dir(day) / agent_id / "state.json"
    if not path.exists():
        return None
    return AgentState.model_validate_json(path.read_text("utf-8"))


def _load_snapshot_relationships(agent_id: str, day: int) -> RelationshipFile:
    """Load agent relationships from a daily snapshot."""
    path = _snapshot_dir(day) / agent_id / "relationships.json"
    if not path.exists():
        return RelationshipFile()
    return RelationshipFile.model_validate_json(path.read_text("utf-8"))


def _load_snapshot_self_narrative(agent_id: str, day: int) -> SelfNarrativeResult:
    """Load structured self-narrative from a daily snapshot."""
    path = _snapshot_dir(day) / agent_id / "self_narrative.json"
    if not path.exists():
        return SelfNarrativeResult()
    return SelfNarrativeResult.model_validate_json(path.read_text("utf-8"))


def _load_scenes_index(day: int) -> list[dict]:
    """Load scenes.json for a given day."""
    path = settings.logs_dir / f"day_{day:03d}" / "scenes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text("utf-8"))


def _load_scene_file(day: int, filename: str) -> dict | None:
    """Load a specific scene JSON file."""
    path = settings.logs_dir / f"day_{day:03d}" / filename
    if not path.exists():
        return None
    return json.loads(path.read_text("utf-8"))


def _reconstruct_today_so_far(agent_id: str, day: int, time_period: str) -> tuple[str, Emotion | None]:
    """Reconstruct what the agent experienced today up to the given time period.

    Returns (formatted_text, latest_emotion_or_None).
    """
    scenes_index = _load_scenes_index(day)
    if not scenes_index:
        return "", None

    # Filter scenes that happened before or at the given time
    tp_idx = TIME_PERIOD_ORDER.index(time_period) if time_period in TIME_PERIOD_ORDER else 0
    completed_scenes = [
        s for s in scenes_index
        if s["time"] in TIME_PERIOD_ORDER
        and TIME_PERIOD_ORDER.index(s["time"]) <= tp_idx
    ]

    if not completed_scenes:
        return "", None

    parts = []
    latest_emotion = None

    for scene_entry in completed_scenes:
        scene_data = _load_scene_file(day, scene_entry["file"])
        if not scene_data:
            continue

        # Find the group this agent was in
        for group in scene_data.get("groups", []):
            if agent_id not in group.get("participants", []):
                continue

            # Extract key moments from narrative
            narrative = group.get("narrative", {})
            key_moments = narrative.get("key_moments", [])
            if key_moments:
                location = scene_data.get("scene", {}).get("location", "未知地点")
                parts.append(f"### {scene_entry['time']} {scene_entry['name']}（{location}）")
                for moment in key_moments:
                    parts.append(f"- {moment}")

            # Extract emotion from reflections
            reflections = group.get("reflections", {})
            if agent_id in reflections:
                ref = reflections[agent_id]
                if isinstance(ref, dict) and "emotion" in ref:
                    try:
                        latest_emotion = Emotion(ref["emotion"])
                    except ValueError:
                        pass

    return "\n".join(parts), latest_emotion


def build_context_at_timepoint(
    agent_id: str,
    day: int,
    time_period: str,
    world: WorldStorage,
) -> dict:
    """Build full agent context at a specific (day, time_period) point.

    Snapshot semantics:
    - day_N snapshot = agent state at END of Day N = START of Day N+1
    - day_000 = initial state = start of Day 1
    - For viewing Day N, load day_{N-1} snapshot as the baseline
    """
    storage = world.get_agent(agent_id)
    profile = storage.load_profile()

    # Load baseline state from previous day's snapshot
    # Day N morning state = day_{N-1} end-of-day snapshot
    # For Day 1: use day_000 (initial state)
    baseline_day = day - 1 if day > 0 else 0
    state = _load_snapshot_state(agent_id, baseline_day)
    if state is None:
        logger.warning(
            "No snapshot for %s at day_%03d — falling back to live state (may be inaccurate)",
            agent_id, baseline_day,
        )
        state = storage.load_state()

    rels = _load_snapshot_relationships(agent_id, baseline_day)
    narr = _load_snapshot_self_narrative(agent_id, baseline_day)

    # Load key memories filtered to day <= N
    all_memories = storage.load_key_memories()
    filtered_memories = [m for m in all_memories.memories if m.day <= day]
    # Take the most recent/important ones
    filtered_memories.sort(key=lambda m: (m.importance, m.day), reverse=True)
    filtered_memories = filtered_memories[:settings.max_key_memories]

    # Recent summary from storage, filtered to day <= N
    recent_summary = storage.read_recent_md_last_n_days(3, max_day=day)

    # Reconstruct "today so far"
    today_events, scene_emotion = _reconstruct_today_so_far(agent_id, day, time_period)

    # Determine current emotion: scene emotion > baseline state emotion
    current_emotion = scene_emotion if scene_emotion else state.emotion

    # Qualitative labels
    role_desc = "学生" if profile.role == Role.STUDENT else "班主任兼语文老师"

    # Build relationship list with labels
    rels_with_labels = []
    for r in rels.relationships.values():
        rels_with_labels.append({
            **r.model_dump(),
            "label_text": relationship_label(r.favorability, r.trust),
        })

    # Build concerns with intensity labels
    concerns = [
        {**c.model_dump(), "intensity_label": intensity_label(c.intensity)}
        for c in state.active_concerns
    ]

    # Pending intentions
    pending_intentions = [
        i for i in state.daily_plan.intentions if not i.fulfilled
    ]

    return {
        "role_description": role_desc,
        "is_student": profile.role == Role.STUDENT,
        "profile_summary": _profile_summary(profile),
        "relationships": rels_with_labels,
        "today_events": today_events,
        "recent_summary": recent_summary,
        "key_memories": filtered_memories,
        "pending_intentions": pending_intentions,
        "emotion_label": current_emotion.value,
        "energy_label": energy_label(state.energy),
        "pressure_label": pressure_label(state.academic_pressure),
        "active_concerns": concerns,
        "self_narrative": narr.narrative,
        "self_concept": narr.self_concept,
        "current_tensions": narr.current_tensions,
        "inner_conflicts": profile.inner_conflicts,
        # Raw data for endpoint use
        "_profile": profile,
        "_state": state,
        "_emotion": current_emotion,
    }
