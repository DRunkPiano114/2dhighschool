"""Tests for catalyst checker (PR4)."""

import json
import random
from pathlib import Path

from sim.config import settings
from sim.models.agent import (
    Academics,
    ActiveConcern,
    AgentProfile,
    AgentState,
    DailyPlan,
    FamilyBackground,
    Gender,
    Intention,
    OverallRank,
    PressureLevel,
    Role,
)
from sim.models.event import EventQueue
from sim.models.relationship import Relationship, RelationshipFile
from sim.world.catalyst import CatalystChecker
from sim.world.event_queue import EventQueueManager


def _profile(aid: str, name: str, role: Role = Role.STUDENT) -> AgentProfile:
    return AgentProfile(
        agent_id=aid, name=name, gender=Gender.MALE, role=role,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )


def _isolated_state() -> AgentState:
    return AgentState()


def _em() -> EventQueueManager:
    return EventQueueManager(EventQueue(), random.Random(0))


def _write_catalyst_file(tmp_path: Path, content: dict) -> Path:
    p = tmp_path / "catalysts.json"
    p.write_text(json.dumps(content, ensure_ascii=False), "utf-8")
    return p


def test_check_trigger_yields_multiple_matches(tmp_path, monkeypatch):
    """PR4: a single isolation trigger must fire for every eligible agent on
    the same day, not just the first match."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "isolation",
                "trigger_params": {"max_active_relationships": 2},
                "templates": ["{agent}被动隔离"],
                "cooldown_days": 7,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    agents = {
        "a": (_profile("a", "A"), _isolated_state()),
        "b": (_profile("b", "B"), _isolated_state()),
        "c": (_profile("c", "C"), _isolated_state()),
    }
    rels = {aid: RelationshipFile() for aid in agents}
    fired = checker.check_and_inject(day=1, agents=agents, relationships=rels, event_manager=_em())
    assert len(fired) == 3


def test_cooldown_scoped_per_agent_not_global(tmp_path, monkeypatch):
    """Two agents independently isolated — both should fire day 1;
    next day, both should be on cooldown but not other agents."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "isolation",
                "trigger_params": {"max_active_relationships": 2},
                "templates": ["{agent}被动隔离"],
                "cooldown_days": 7,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    agents = {
        "a": (_profile("a", "A"), _isolated_state()),
        "b": (_profile("b", "B"), _isolated_state()),
    }
    rels = {aid: RelationshipFile() for aid in agents}
    d1 = checker.check_and_inject(day=1, agents=agents, relationships=rels, event_manager=_em())
    d2 = checker.check_and_inject(day=2, agents=agents, relationships=rels, event_manager=_em())
    assert len(d1) == 2
    assert len(d2) == 0  # both on per-agent cooldown


def test_cooldown_scoped_per_pair(tmp_path, monkeypatch):
    """relationship_threshold trigger is 2-agent witness → per-pair cooldown
    key; distinct pairs with distinct members can still fire independently."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "relationship_threshold",
                "trigger_params": {"favorability_gte": 10},
                "templates": ["{agent_a}和{agent_b}走得近"],
                "cooldown_days": 21,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    agents = {
        "a": (_profile("a", "A"), AgentState()),
        "b": (_profile("b", "B"), AgentState()),
        "c": (_profile("c", "C"), AgentState()),
    }
    rels = {
        "a": RelationshipFile(relationships={
            "b": Relationship(target_name="B", target_id="b", favorability=15),
        }),
        "b": RelationshipFile(relationships={
            "a": Relationship(target_name="A", target_id="a", favorability=15),
        }),
        "c": RelationshipFile(),
    }
    fired = checker.check_and_inject(
        day=1, agents=agents, relationships=rels, event_manager=_em(),
    )
    # ONE firing for pair (a, b) — seen_pairs dedup within the same day.
    assert len(fired) == 1


def test_concern_stalled_with_people_triggers_relational_only(tmp_path, monkeypatch):
    """Sig6 regression: a concern with related_people should fire only the
    -relational entry, not -generic, despite both existing."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "concern_stalled",
                "trigger_params": {
                    "min_stale_days": 4, "topic": "人际矛盾",
                    "require_related_people": True,
                },
                "templates": ["{agent}碰到{related_person}"],
                "cooldown_days": 5,
            },
            {
                "trigger_type": "concern_stalled",
                "trigger_params": {
                    "min_stale_days": 4, "topic": "人际矛盾",
                    "require_empty_related_people": True,
                },
                "templates": ["{agent}心里别扭"],
                "cooldown_days": 5,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="跟江浩天闹僵", topic="人际矛盾",
            related_people=["江浩天"], intensity=6,
            last_new_info_day=0,
        ),
    ])
    agents = {"a": (_profile("a", "小明"), state)}
    rels = {"a": RelationshipFile()}
    fired = checker.check_and_inject(
        day=5, agents=agents, relationships=rels, event_manager=_em(),
    )
    assert len(fired) == 1
    assert "江浩天" in fired[0]
    assert "心里别扭" not in fired[0]


def test_concern_stalled_empty_people_triggers_generic_only(tmp_path, monkeypatch):
    """Sig6 regression: a concern with no related_people should fire only
    the -generic entry (no KeyError from missing {related_person})."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "concern_stalled",
                "trigger_params": {
                    "min_stale_days": 4, "topic": "人际矛盾",
                    "require_related_people": True,
                },
                "templates": ["{agent}碰到{related_person}"],
                "cooldown_days": 5,
            },
            {
                "trigger_type": "concern_stalled",
                "trigger_params": {
                    "min_stale_days": 4, "topic": "人际矛盾",
                    "require_empty_related_people": True,
                },
                "templates": ["{agent}心里别扭"],
                "cooldown_days": 5,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="上次那场风波", topic="人际矛盾",
            related_people=[], intensity=6,
            last_new_info_day=0,
        ),
    ])
    agents = {"a": (_profile("a", "小明"), state)}
    rels = {"a": RelationshipFile()}
    fired = checker.check_and_inject(
        day=5, agents=agents, relationships=rels, event_manager=_em(),
    )
    assert len(fired) == 1
    assert "心里别扭" in fired[0]


def test_legacy_cooldown_keys_dropped_on_load(tmp_path, monkeypatch):
    """PR4 migration: a pre-PR4 cooldown state file (keys without the
    `:witness` suffix after the json body) should be filtered on load."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    # Write a pre-PR4 style cooldown state: key with NO suffix after `}`
    legacy_state = {
        'concern_stalled:{"min_stale_days": 4, "topic": "人际矛盾"}': 1,
        # Post-PR4 style: has ":<suffix>" after `}`
        'isolation:{"max_active_relationships": 2}:agent_a': 2,
    }
    (tmp_path / "catalyst_cooldowns.json").write_text(
        json.dumps(legacy_state, ensure_ascii=False), "utf-8",
    )
    cat_file = _write_catalyst_file(tmp_path, {"catalyst_events": []})
    checker = CatalystChecker(cat_file, random.Random(0))
    # Legacy dropped, modern kept.
    assert 'concern_stalled:{"min_stale_days": 4, "topic": "人际矛盾"}' not in checker.cooldown_state
    assert 'isolation:{"max_active_relationships": 2}:agent_a' in checker.cooldown_state


def test_intention_stalled_per_agent_not_spammed(tmp_path, monkeypatch):
    """Multiple stalled intentions on the same agent → at most one firing per
    agent per day for this trigger."""
    monkeypatch.setattr(settings, "world_dir", tmp_path)
    cat_file = _write_catalyst_file(tmp_path, {
        "catalyst_events": [
            {
                "trigger_type": "intention_stalled",
                "trigger_params": {"min_pursued_days": 3},
                "templates": ["{agent}不得不面对"],
                "cooldown_days": 7,
            },
        ],
    })
    checker = CatalystChecker(cat_file, random.Random(0))
    state = AgentState(daily_plan=DailyPlan(intentions=[
        Intention(target="X", goal="a", reason="r", pursued_days=5),
        Intention(target="Y", goal="b", reason="r", pursued_days=5),
    ]))
    agents = {"a": (_profile("a", "A"), state)}
    rels = {"a": RelationshipFile()}
    fired = checker.check_and_inject(
        day=1, agents=agents, relationships=rels, event_manager=_em(),
    )
    assert len(fired) == 1
