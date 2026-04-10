"""Tests for free-period location data flow.

Covers:
- SceneConfig validator: free periods must declare pref_field, valid_locations,
  and a default location that lives inside valid_locations. The pref_field is a
  Literal so typos fail at parse time.
- SceneGenerator._generate_free_period_scenes: groups students by their
  preference, falls back to config.location for invalid prefs, and routes the
  teacher to default_location.
- daily_plan validation: invalid LLM-generated location for a slot falls back
  to that slot's cfg.location, leaving valid slots untouched.
"""

import asyncio
from random import Random
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sim.agent.daily_plan import generate_daily_plan
from sim.llm.client import LLMResult
from sim.models.agent import (
    Academics, AgentProfile, AgentState, DailyPlan, Emotion, FamilyBackground,
    Gender, LocationPreference, OverallRank, PressureLevel, Role,
)
from sim.models.scene import SceneConfig, SceneDensity
from sim.world.scene_generator import SceneGenerator


# --- helpers ---

def _make_free_period_config(
    *,
    time: str = "08:45",
    name: str = "课间",
    location: str = "教室",
    valid_locations: list[str] | None = None,
    pref_field: str | None = "morning_break",
) -> SceneConfig:
    return SceneConfig(
        time=time,
        name=name,
        location=location,
        density=SceneDensity.HIGH,
        max_rounds=20,
        is_free_period=True,
        valid_locations=valid_locations or ["教室", "走廊", "操场"],
        pref_field=pref_field,  # type: ignore[arg-type]
    )


def _make_student(aid: str, name: str) -> AgentProfile:
    return AgentProfile(
        agent_id=aid, name=name, gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )


def _make_teacher() -> AgentProfile:
    return AgentProfile(
        agent_id="he_min", name="何敏", gender=Gender.FEMALE,
        role=Role.HOMEROOM_TEACHER,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.LOW),
    )


def _state_with_pref(**prefs) -> AgentState:
    return AgentState(daily_plan=DailyPlan(
        location_preferences=LocationPreference(**prefs),
    ))


# --- SceneConfig validator ---

def test_free_period_requires_pref_field():
    """A free period without pref_field must fail at parse time."""
    with pytest.raises(ValidationError) as exc:
        SceneConfig(
            time="08:45", name="课间", location="教室",
            density=SceneDensity.HIGH, is_free_period=True,
            valid_locations=["教室", "走廊"],
            pref_field=None,
        )
    assert "pref_field" in str(exc.value)


def test_free_period_requires_valid_locations():
    """A free period without valid_locations must fail at parse time."""
    with pytest.raises(ValidationError) as exc:
        SceneConfig(
            time="08:45", name="课间", location="教室",
            density=SceneDensity.HIGH, is_free_period=True,
            valid_locations=[],
            pref_field="morning_break",
        )
    assert "valid_locations" in str(exc.value)


def test_free_period_default_location_must_be_in_valid_locations():
    """If location isn't in valid_locations, the fallback semantics break — fail."""
    with pytest.raises(ValidationError) as exc:
        SceneConfig(
            time="12:00", name="午饭", location="操场",
            density=SceneDensity.HIGH, is_free_period=True,
            valid_locations=["食堂", "教室"],
            pref_field="lunch",
        )
    assert "valid_locations" in str(exc.value)


def test_free_period_pref_field_literal_rejects_typo():
    """Literal type rejects unknown pref_field values (e.g. typos)."""
    with pytest.raises(ValidationError):
        SceneConfig(
            time="08:45", name="课间", location="教室",
            density=SceneDensity.HIGH, is_free_period=True,
            valid_locations=["教室"],
            pref_field="morrning_break",  # typo  # type: ignore[arg-type]
        )


def test_free_period_valid_parses():
    """A well-formed free period parses without error."""
    cfg = SceneConfig(
        time="12:00", name="午饭", location="食堂",
        density=SceneDensity.HIGH, is_free_period=True,
        valid_locations=["食堂", "教室", "操场", "小卖部"],
        pref_field="lunch",
    )
    assert cfg.pref_field == "lunch"
    assert cfg.location in cfg.valid_locations


def test_normal_scene_does_not_require_pref_field():
    """Non-free-period scenes don't need pref_field/valid_locations."""
    cfg = SceneConfig(
        time="07:00", name="早读", location="教室",
        density=SceneDensity.LOW,
    )
    assert cfg.pref_field is None
    assert cfg.valid_locations == []
    assert cfg.is_free_period is False


# --- SceneGenerator._generate_free_period_scenes ---

def test_free_period_groups_by_pref_field():
    """Students with different pref_field values land in different scenes."""
    cfg = _make_free_period_config(
        valid_locations=["教室", "走廊", "操场"],
        pref_field="morning_break",
    )
    profiles = {
        "a": _make_student("a", "张伟"),
        "b": _make_student("b", "李明"),
        "c": _make_student("c", "王芳"),
    }
    states = {
        "a": _state_with_pref(morning_break="走廊"),
        "b": _state_with_pref(morning_break="走廊"),
        "c": _state_with_pref(morning_break="操场"),
    }
    # Pin RNG so the teacher (absent here) wouldn't affect anything anyway.
    gen = SceneGenerator(profiles, states, [cfg], rng=Random(0))
    scenes = gen.generate_scenes_for_config(cfg, day=1, start_index=0)
    by_loc = {s.location: sorted(s.agent_ids) for s in scenes}
    assert by_loc == {"走廊": ["a", "b"], "操场": ["c"]}


def test_free_period_uses_pref_field_from_config_not_time():
    """If schedule.json declared a different pref_field, the generator must
    follow it. (Regression: the old code mapped time → pref_field via a
    hardcoded private dict; this test pins the new contract.)"""
    cfg = _make_free_period_config(
        time="09:99",  # nonsense time the old _TIME_TO_PREF_FIELD wouldn't know
        valid_locations=["教室", "操场"],
        pref_field="afternoon_break",  # explicitly use afternoon_break for this slot
    )
    profiles = {"a": _make_student("a", "张伟")}
    states = {"a": _state_with_pref(
        morning_break="教室",       # ignored — pref_field is afternoon_break
        afternoon_break="操场",     # this is the one that should be read
    )}
    gen = SceneGenerator(profiles, states, [cfg], rng=Random(0))
    scenes = gen.generate_scenes_for_config(cfg, day=1, start_index=0)
    assert len(scenes) == 1
    assert scenes[0].location == "操场"
    assert scenes[0].agent_ids == ["a"]


def test_free_period_invalid_pref_falls_back_to_default_location():
    """A student whose preference isn't in valid_locations defaults to config.location."""
    cfg = _make_free_period_config(
        location="教室",
        valid_locations=["教室", "走廊", "操场"],
        pref_field="morning_break",
    )
    profiles = {"a": _make_student("a", "张伟")}
    states = {"a": _state_with_pref(morning_break="月球")}  # not a valid location
    gen = SceneGenerator(profiles, states, [cfg], rng=Random(0))
    scenes = gen.generate_scenes_for_config(cfg, day=1, start_index=0)
    assert len(scenes) == 1
    assert scenes[0].location == "教室"
    assert scenes[0].agent_ids == ["a"]


def test_free_period_no_daily_plan_falls_back_to_default_location():
    """A student with no daily_plan still gets routed to config.location."""
    cfg = _make_free_period_config(
        location="教室",
        valid_locations=["教室", "走廊"],
        pref_field="morning_break",
    )
    profiles = {"a": _make_student("a", "张伟")}
    states = {"a": AgentState()}  # no plan set
    gen = SceneGenerator(profiles, states, [cfg], rng=Random(0))
    scenes = gen.generate_scenes_for_config(cfg, day=1, start_index=0)
    assert len(scenes) == 1
    assert scenes[0].location == "教室"


def test_free_period_teacher_joins_default_location():
    """When the teacher rolls in, she joins config.location, not a hardcoded one."""
    cfg = _make_free_period_config(
        time="12:00", name="午饭", location="食堂",
        valid_locations=["食堂", "教室", "操场"],
        pref_field="lunch",
    )
    profiles = {
        "a": _make_student("a", "张伟"),
        "he_min": _make_teacher(),
    }
    states = {
        "a": _state_with_pref(lunch="操场"),
        "he_min": AgentState(),
    }
    # Find a seed where rng.random() < 0.30 (lunch teacher_prob), so teacher appears.
    teacher_seed = None
    for s in range(100):
        if Random(s).random() < 0.30:
            teacher_seed = s
            break
    assert teacher_seed is not None
    gen = SceneGenerator(profiles, states, [cfg], rng=Random(teacher_seed))
    scenes = gen.generate_scenes_for_config(cfg, day=1, start_index=0)
    by_loc = {s.location: sorted(s.agent_ids) for s in scenes}
    # Teacher must land in 食堂 (= config.location), not in the student's 操场 group.
    assert "he_min" in by_loc.get("食堂", [])
    assert "he_min" not in by_loc.get("操场", [])


def test_scene_generator_requires_schedule():
    """SceneGenerator no longer loads schedule itself — schedule is required."""
    profiles = {"a": _make_student("a", "张伟")}
    states = {"a": AgentState()}
    # Should not raise — passing an empty schedule is fine, the generator just
    # won't have anything to iterate via legacy generate_day().
    gen = SceneGenerator(profiles, states, [], rng=Random(0))
    assert gen.schedule == []


# --- daily_plan validation ---

def _fake_daily_plan_result(prefs: LocationPreference) -> LLMResult:
    return LLMResult(
        data=DailyPlan(
            intentions=[],
            mood_forecast=Emotion.NEUTRAL,
            location_preferences=prefs,
        ),
        tokens_prompt=10,
        tokens_completion=5,
        cost_usd=0.001,
    )


def _make_storage_mock():
    """Build a storage mock with the surface generate_daily_plan touches."""
    from unittest.mock import MagicMock
    storage = MagicMock()
    storage.load_relationships.return_value = MagicMock(relationships={})
    storage.read_recent_md_last_n_days.return_value = ""
    narr = MagicMock()
    narr.narrative = ""
    narr.self_concept = []
    narr.current_tensions = []
    storage.load_self_narrative_structured.return_value = narr
    return storage


def test_daily_plan_validation_falls_back_per_slot():
    """Per-slot fallback: invalid morning_break → config.location for that slot,
    while a valid lunch is left untouched."""
    morning_cfg = _make_free_period_config(
        time="08:45", name="课间", location="教室",
        valid_locations=["教室", "走廊", "操场"],
        pref_field="morning_break",
    )
    lunch_cfg = _make_free_period_config(
        time="12:00", name="午饭", location="食堂",
        valid_locations=["食堂", "教室", "操场"],
        pref_field="lunch",
    )

    # LLM returns: morning_break=月球 (invalid), lunch=操场 (valid)
    bad_prefs = LocationPreference(morning_break="月球", lunch="操场", afternoon_break="教室")
    fake_result = _fake_daily_plan_result(bad_prefs)

    profile = _make_student("a", "张伟")
    state = AgentState()
    storage = _make_storage_mock()

    async def fake_call(*args, **kwargs):
        return fake_result

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        plan = asyncio.run(generate_daily_plan(
            "a", storage, profile, state,
            next_exam_in_days=20, day=1,
            free_period_configs=[morning_cfg, lunch_cfg],
        ))

    # morning_break was invalid → must fall back to morning_cfg.location ("教室")
    assert plan.location_preferences.morning_break == "教室"
    # lunch was valid ("操场" is in lunch_cfg.valid_locations) → unchanged
    assert plan.location_preferences.lunch == "操场"


def test_daily_plan_validation_skipped_when_no_free_periods():
    """If the schedule has no free periods, the LLM's prefs pass through untouched."""
    bad_prefs = LocationPreference(morning_break="月球", lunch="火星", afternoon_break="海底")
    fake_result = _fake_daily_plan_result(bad_prefs)

    profile = _make_student("a", "张伟")
    state = AgentState()
    storage = _make_storage_mock()

    async def fake_call(*args, **kwargs):
        return fake_result

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        plan = asyncio.run(generate_daily_plan(
            "a", storage, profile, state,
            next_exam_in_days=20, day=1,
            free_period_configs=[],
        ))

    # No free period configs to validate against → LLM output preserved as-is.
    assert plan.location_preferences.morning_break == "月球"
    assert plan.location_preferences.lunch == "火星"
