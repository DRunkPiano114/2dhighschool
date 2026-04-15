"""Tests for time-travel context assembly (src/sim/api/context.py)."""

import json
import shutil
from pathlib import Path

import pytest

from sim.api.context import (
    TIME_PERIOD_ORDER,
    _load_scenes_index,
    _load_snapshot_relationships,
    _load_snapshot_self_narrative,
    _load_snapshot_state,
    _reconstruct_today_so_far,
    build_context_at_timepoint,
)
from sim.config import settings
from sim.models.agent import AgentProfile, AgentState, Emotion, Gender, Role, Academics, FamilyBackground, PressureLevel, OverallRank
from sim.agent.storage import WorldStorage, atomic_write_json


@pytest.fixture
def tmp_world(tmp_path):
    """Create a temp world with one agent and snapshot directories."""
    agents_dir = tmp_path / "agents"
    world_dir = tmp_path / "world"
    days_dir = tmp_path / "days"
    for d in [agents_dir, world_dir, days_dir]:
        d.mkdir()

    # Create agent profile + state
    agent_id = "test_agent"
    agent_dir = agents_dir / agent_id
    agent_dir.mkdir()

    profile = AgentProfile(
        agent_id=agent_id,
        name="测试同学",
        gender=Gender.MALE,
        role=Role.STUDENT,
        personality=["内向", "安静"],
        speaking_style="说话很少",
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        backstory="普通学生",
    )
    atomic_write_json(agent_dir / "profile.json", profile.model_dump())

    state = AgentState(emotion=Emotion.NEUTRAL, energy=80, academic_pressure=40)
    atomic_write_json(agent_dir / "state.json", state.model_dump())

    # Create empty relationships
    atomic_write_json(agent_dir / "relationships.json", {"relationships": {}})
    atomic_write_json(agent_dir / "key_memories.json", {"memories": []})
    atomic_write_json(agent_dir / "self_narrative.json", {"narrative": "", "self_concept": [], "current_tensions": []})

    # Monkey-patch settings for test
    old_agents = settings.agents_dir
    old_world = settings.world_dir
    old_days = settings.days_dir
    settings.agents_dir = agents_dir
    settings.world_dir = world_dir
    settings.days_dir = days_dir

    # Create WorldStorage
    world = WorldStorage(agents_dir=agents_dir, world_dir=world_dir)
    world.load_all_agents()

    yield {
        "world": world,
        "agent_id": agent_id,
        "agents_dir": agents_dir,
        "days_dir": days_dir,
        "profile": profile,
        "state": state,
    }

    settings.agents_dir = old_agents
    settings.world_dir = old_world
    settings.days_dir = old_days


class TestSnapshotLoading:
    """Test loading state from daily snapshots."""

    def test_load_snapshot_state_missing(self, tmp_world):
        """Returns None when snapshot doesn't exist."""
        result = _load_snapshot_state(tmp_world["agent_id"], 0)
        assert result is None

    def test_load_snapshot_state_exists(self, tmp_world):
        """Loads state from snapshot directory."""
        snap_dir = tmp_world["days_dir"] / "day_000" / "agent_snapshots" / tmp_world["agent_id"]
        snap_dir.mkdir(parents=True)
        state = AgentState(emotion=Emotion.HAPPY, energy=90, academic_pressure=20)
        atomic_write_json(snap_dir / "state.json", state.model_dump())

        result = _load_snapshot_state(tmp_world["agent_id"], 0)
        assert result is not None
        assert result.emotion == Emotion.HAPPY
        assert result.energy == 90

    def test_load_snapshot_relationships_missing(self, tmp_world):
        """Returns empty RelationshipFile when no snapshot."""
        result = _load_snapshot_relationships(tmp_world["agent_id"], 0)
        assert len(result.relationships) == 0

    def test_load_snapshot_self_narrative_missing(self, tmp_world):
        """Returns empty SelfNarrativeResult when no snapshot."""
        result = _load_snapshot_self_narrative(tmp_world["agent_id"], 0)
        assert result.narrative == ""


class TestTimeTravel:
    """Test the full context assembly at a timepoint."""

    def test_build_context_no_snapshots_fallback(self, tmp_world, caplog):
        """Falls back to live agent state when no snapshots exist, with warning."""
        import logging
        with caplog.at_level(logging.WARNING, logger="sim.api.context"):
            ctx = build_context_at_timepoint(
                tmp_world["agent_id"], 1, "08:45", tmp_world["world"]
            )
        assert "profile_summary" in ctx
        assert ctx["energy_label"] is not None
        assert ctx["pressure_label"] is not None
        assert ctx["emotion_label"] is not None
        # Should have logged a warning about missing snapshot
        assert any("falling back to live state" in r.message for r in caplog.records)

    def test_build_context_with_day0_snapshot(self, tmp_world):
        """Uses Day 0 snapshot as baseline for Day 1."""
        snap_dir = tmp_world["days_dir"] / "day_000" / "agent_snapshots" / tmp_world["agent_id"]
        snap_dir.mkdir(parents=True)
        state = AgentState(emotion=Emotion.EXCITED, energy=95, academic_pressure=10)
        atomic_write_json(snap_dir / "state.json", state.model_dump())
        atomic_write_json(snap_dir / "relationships.json", {"relationships": {}})
        atomic_write_json(snap_dir / "self_narrative.json", {"narrative": "我是开心的", "self_concept": [], "current_tensions": []})

        ctx = build_context_at_timepoint(
            tmp_world["agent_id"], 1, "08:45", tmp_world["world"]
        )
        # Should use day_000 snapshot (day 1 baseline = day_000)
        assert ctx["emotion_label"] == "excited"
        assert ctx["self_narrative"] == "我是开心的"

    def test_build_context_includes_key_memories_filtered(self, tmp_world):
        """Key memories are filtered to day <= N."""
        agent_dir = tmp_world["agents_dir"] / tmp_world["agent_id"]
        atomic_write_json(agent_dir / "key_memories.json", {
            "memories": [
                {"date": "Day 1", "day": 1, "text": "day 1 memory", "importance": 7},
                {"date": "Day 2", "day": 2, "text": "day 2 memory", "importance": 8},
                {"date": "Day 5", "day": 5, "text": "future memory", "importance": 9},
            ]
        })

        ctx = build_context_at_timepoint(
            tmp_world["agent_id"], 2, "08:45", tmp_world["world"]
        )
        # Only day 1 and 2 memories, not day 5
        mem_texts = [m.text for m in ctx["key_memories"]]
        assert "day 1 memory" in mem_texts
        assert "day 2 memory" in mem_texts
        assert "future memory" not in mem_texts


class TestTodaySoFar:
    """Test reconstruction of what happened today."""

    def test_no_scenes(self, tmp_world):
        """Returns empty when no scenes exist."""
        text, emotion = _reconstruct_today_so_far(tmp_world["agent_id"], 1, "08:45")
        assert text == ""
        assert emotion is None

    def test_scenes_index_loading(self, tmp_world):
        """Loads scenes.json correctly."""
        day_dir = tmp_world["days_dir"] / "day_001"
        day_dir.mkdir(parents=True)
        atomic_write_json(day_dir / "scenes.json", [
            {"scene_index": 0, "time": "08:45", "name": "课间", "location": "教室", "file": "0845_课间.json", "groups": []},
        ])

        result = _load_scenes_index(1)
        assert len(result) == 1
        assert result[0]["time"] == "08:45"

    def test_time_period_ordering(self):
        """Time periods are in chronological order."""
        assert TIME_PERIOD_ORDER == ["08:45", "12:00", "15:30", "22:00"]
