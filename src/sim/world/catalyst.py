"""Catalyst event checker — fires conditional events based on agent state."""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from ..config import settings
from ..models.agent import AgentProfile, AgentState, Role
from ..models.relationship import RelationshipFile
from .event_queue import EventQueueManager


class CatalystChecker:
    """Check triggers once per day and inject matching events into EventQueue.

    PR4 changes (vs pre-PR4):
      - `_check_trigger` is a generator; each catalyst can fire for multiple
        matching agents on the same day (previously the first match would
        `return`, starving other eligible agents).
      - Cooldown is always per-agent (or per-pair for 2-agent witnesses).
        Previously a global cooldown on a trigger starved every other agent
        that day; scope is inferred from the witnesses list.
      - The `人际矛盾` and `学业焦虑` catalysts in `data/catalyst_events.json`
        are split into `-relational` and `-generic` entries. `-relational`
        requires `related_people` non-empty via `require_related_people=True`;
        `-generic` requires empty via `require_empty_related_people=True`.
        The two are mutually exclusive so the same concern can't double-fire.
      - Legacy cooldown keys (from the pre-PR4 format without a witness
        suffix) are dropped on load. One-day effect is a small catalyst
        burst as cleared-cooldown concerns fire; called out in the changelog.
    """

    def __init__(self, catalyst_file: Path, rng: random.Random):
        self.catalysts = json.loads(catalyst_file.read_text("utf-8"))["catalyst_events"]
        self.rng = rng
        self.cooldown_state: dict[str, int] = self._load_cooldown_state()

    def check_and_inject(
        self,
        day: int,
        agents: dict[str, tuple[AgentProfile, AgentState]],
        relationships: dict[str, RelationshipFile],
        event_manager: EventQueueManager,
    ) -> list[str]:
        """Check triggers and inject matching events. Returns fired event texts."""
        fired: list[str] = []
        for catalyst in self.catalysts:
            # Iterate ALL matches this catalyst produced, not just the first.
            for matched in self._check_trigger(catalyst, day, agents, relationships):
                cooldown_key = self._cooldown_key(catalyst, matched)
                if self._on_cooldown(cooldown_key, catalyst["cooldown_days"], day):
                    continue
                event_text = self._fill_template(catalyst, matched)
                event_manager.add_event(
                    text=event_text,
                    category="catalyst",
                    source_scene="catalyst",
                    source_day=day,
                    witnesses=matched.get("witnesses", []),
                    spread_probability=0.7,
                )
                self.cooldown_state[cooldown_key] = day
                fired.append(event_text)
        self._save_cooldown_state()
        return fired

    # -- Cooldown management --

    def _cooldown_key(self, catalyst: dict, matched: dict) -> str:
        """Always produces a scoped key. A 1-agent witness list → per-agent;
        a 2-agent witness list → per-pair. Global cooldown is no longer
        supported — it starved every agent-except-the-first-match per day."""
        base = (
            f"{catalyst['trigger_type']}:"
            f"{json.dumps(catalyst['trigger_params'], sort_keys=True, ensure_ascii=False)}"
        )
        witnesses = matched.get("witnesses", [])
        # Sorted so per-pair keys are order-invariant.
        suffix = ":".join(sorted(witnesses)) if witnesses else "global"
        return f"{base}:{suffix}"

    def _on_cooldown(self, key: str, cooldown_days: int, today: int) -> bool:
        last_fired = self.cooldown_state.get(key, -999)
        return (today - last_fired) < cooldown_days

    def _load_cooldown_state(self) -> dict[str, int]:
        """Load cooldown state, filtering out any pre-PR4 keys missing the
        witness suffix. A pre-PR4 key had two ':' separators (trigger_type
        and trigger_params JSON); PR4 adds a third for the scope suffix.

        Dropping instead of rewriting is intentional: the scope suffix
        depends on which agents matched and we don't have that context at
        load time. One-day migration effect: any concern whose backlog was
        held by a legacy global cooldown fires on day 1, which is visible
        but harmless — documented in the PR4 changelog."""
        path = settings.world_dir / "catalyst_cooldowns.json"
        if not path.exists():
            return {}
        raw = json.loads(path.read_text("utf-8"))
        if not isinstance(raw, dict):
            return {}

        legacy: list[str] = []
        kept: dict[str, int] = {}
        for k, v in raw.items():
            # Pre-PR4 keys have the form "<trigger_type>:<params_json>".
            # The params json is structured so a legit post-PR4 key has
            # exactly one additional ":<suffix>" appended. A cheap check:
            # if the key lacks a final ":<non-empty>" that isn't part of
            # the json body, it's legacy. We use a robust heuristic:
            # post-PR4 keys always end with ":global" or ":<agent_or_pair>".
            # The json body always ends with "}". If the character after
            # the last "}" is ":" and there is content after it, it's new;
            # otherwise legacy.
            idx = k.rfind("}")
            if idx == -1 or idx >= len(k) - 1 or k[idx + 1] != ":":
                legacy.append(k)
                continue
            kept[k] = v

        if legacy:
            logger.info(
                f"catalyst cooldowns: dropped {len(legacy)} legacy keys "
                f"on migration (PR4 scope refactor)"
            )
        return kept

    def _save_cooldown_state(self) -> None:
        path = settings.world_dir / "catalyst_cooldowns.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.cooldown_state, ensure_ascii=False, indent=2), "utf-8",
        )

    # -- Trigger checking --

    def _check_trigger(
        self,
        catalyst: dict,
        day: int,
        agents: dict[str, tuple[AgentProfile, AgentState]],
        relationships: dict[str, RelationshipFile],
    ) -> Iterator[dict]:
        """Yield every matching entry. Generator: caller iterates across
        all agents that independently meet the condition, not just the first."""
        trigger_type = catalyst["trigger_type"]
        params = catalyst["trigger_params"]

        if trigger_type == "concern_stalled":
            for aid, (profile, state) in agents.items():
                if profile.role != Role.STUDENT:
                    continue
                for c in state.active_concerns:
                    if c.topic != params["topic"]:
                        continue
                    # -relational / -generic mutex: entries in
                    # data/catalyst_events.json carry either
                    # require_related_people or require_empty_related_people.
                    if params.get("require_related_people") and not c.related_people:
                        continue
                    if params.get("require_empty_related_people") and c.related_people:
                        continue
                    # PR3: drives off last_new_info_day so pure emotion
                    # reinforcement doesn't mask a stalled concern.
                    stale_days = day - c.last_new_info_day
                    if stale_days < params["min_stale_days"]:
                        continue
                    result: dict = {
                        "agent": profile.name,
                        "agent_id": aid,
                        "witnesses": [aid],
                    }
                    if c.related_people:
                        result["related_person"] = c.related_people[0]
                    yield result

        elif trigger_type == "isolation":
            for aid, (profile, state) in agents.items():
                if profile.role != Role.STUDENT:
                    continue
                rels = relationships.get(aid)
                if not rels:
                    continue
                active_rels = sum(
                    1 for rel in rels.relationships.values()
                    if rel.days_since_interaction <= 3
                )
                if active_rels <= params["max_active_relationships"]:
                    yield {
                        "agent": profile.name,
                        "agent_id": aid,
                        "witnesses": [aid],
                    }

        elif trigger_type == "relationship_threshold":
            seen_pairs: set[str] = set()
            for aid, (profile_a, _) in agents.items():
                if profile_a.role != Role.STUDENT:
                    continue
                rels = relationships.get(aid)
                if not rels:
                    continue
                for rel in rels.relationships.values():
                    if rel.favorability < params["favorability_gte"]:
                        continue
                    other_id = rel.target_id
                    other = agents.get(other_id)
                    if not other or other[0].role != Role.STUDENT:
                        continue
                    pair_key = "|".join(sorted([aid, other_id]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    yield {
                        "agent_a": profile_a.name,
                        "agent_b": other[0].name,
                        "witnesses": [aid, other_id],
                    }

        elif trigger_type == "intention_stalled":
            for aid, (profile, state) in agents.items():
                if profile.role != Role.STUDENT:
                    continue
                for intent in state.daily_plan.intentions:
                    if intent.fulfilled or intent.abandoned:
                        continue
                    if intent.pursued_days >= params["min_pursued_days"]:
                        yield {
                            "agent": profile.name,
                            "agent_id": aid,
                            "witnesses": [aid],
                        }
                        break  # one firing per agent per day is enough

    def _fill_template(self, catalyst: dict, matched: dict) -> str:
        template = self.rng.choice(catalyst["templates"])
        return template.format(**{
            k: v for k, v in matched.items()
            if k not in ("witnesses", "agent_id")
        })
