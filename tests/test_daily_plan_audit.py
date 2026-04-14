"""Tests for PR8 daily_plan audit retry (feature-flagged)."""

import asyncio
from unittest.mock import MagicMock, patch

from sim.agent.daily_plan import _reset_audit_budget, generate_daily_plan
from sim.config import settings
from sim.llm.client import LLMResult
from sim.models.agent import (
    Academics, ActiveConcern, AgentProfile, AgentState, DailyPlan, Emotion,
    FamilyBackground, Gender, Intention, LocationPreference, OverallRank,
    PressureLevel, Role,
)


def _student(aid: str, name: str) -> AgentProfile:
    return AgentProfile(
        agent_id=aid, name=name, gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )


def _storage_mock() -> MagicMock:
    storage = MagicMock()
    storage.load_relationships.return_value = MagicMock(relationships={})
    storage.read_recent_md_last_n_days.return_value = ""
    narr = MagicMock()
    narr.narrative = ""
    narr.self_concept = []
    narr.current_tensions = []
    storage.load_self_narrative_structured.return_value = narr
    return storage


def _plan_result(intentions: list[Intention]) -> LLMResult:
    return LLMResult(
        data=DailyPlan(
            intentions=intentions,
            mood_forecast=Emotion.NEUTRAL,
            location_preferences=LocationPreference(),
        ),
        tokens_prompt=10, tokens_completion=5, cost_usd=0.001,
    )


def _state_with_strong_concern() -> AgentState:
    """State with one concern at intensity=8, related_people in profiles."""
    return AgentState(active_concerns=[
        ActiveConcern(
            text="被父亲责骂数学成绩", id="deadbe",
            topic="家庭压力", related_people=["父亲"], intensity=8,
            last_new_info_day=3, last_reinforced_day=3,
        ),
    ])


def _unhooked_intentions() -> list[Intention]:
    """Intentions that don't hook the strong concern."""
    return [Intention(target="陆思远", goal="问作业", reason="x", satisfies_concern=None)]


def _hooked_intentions() -> list[Intention]:
    return [Intention(
        target="父亲", goal="找爸爸聊化学", reason="必须面对",
        satisfies_concern="deadbe",
    )]


def _all_profiles() -> dict[str, AgentProfile]:
    return {"a": _student("a", "张伟"), "dad": _student("dad", "父亲")}


def test_audit_flag_off_only_warns(monkeypatch, caplog):
    """Default: flag=False → only warning, no retry LLM call."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", False)

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _plan_result(_unhooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"),
            _state_with_strong_concern(),
            next_exam_in_days=20, day=1,
            all_profiles=_all_profiles(),
        ))

    assert call_count == 1  # no retry


def test_audit_flag_on_fails_retries_once(monkeypatch):
    """Flag=on, first call unhooked → one retry, retry hooks → final plan hooks."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", True)

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _plan_result(_unhooked_intentions())
        return _plan_result(_hooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        plan = asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"),
            _state_with_strong_concern(),
            next_exam_in_days=20, day=1,
            all_profiles=_all_profiles(),
        ))

    assert call_count == 2
    assert plan.intentions[0].satisfies_concern == "deadbe"


def test_audit_flag_on_fails_twice_accepts_plan(monkeypatch):
    """Flag=on, both calls unhooked → only one retry, second failure just warns.
    per_call budget = 1 — we never retry a retry."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", True)

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _plan_result(_unhooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        plan = asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"),
            _state_with_strong_concern(),
            next_exam_in_days=20, day=1,
            all_profiles=_all_profiles(),
        ))

    assert call_count == 2  # initial + one retry, never a third
    assert plan.intentions[0].satisfies_concern is None  # unhooked retry plan returned


def test_audit_per_day_budget_prevents_second_retry_same_day(monkeypatch):
    """Two generate_daily_plan calls for the same agent on the same day:
    first consumes the budget, second does not retry."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", True)
    monkeypatch.setattr(
        settings, "daily_plan_audit_max_retries_per_day_per_agent", 1,
    )

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _plan_result(_unhooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        for _ in range(2):
            asyncio.run(generate_daily_plan(
                "a", _storage_mock(), _student("a", "张伟"),
                _state_with_strong_concern(),
                next_exam_in_days=20, day=1,
                all_profiles=_all_profiles(),
            ))

    # First run: initial + retry = 2 calls. Second run: initial only = 1 call.
    # Total = 3. (If the budget weren't per-day, we'd see 4.)
    assert call_count == 3


def test_audit_per_day_budget_resets_next_day(monkeypatch):
    """Sig9 regression: moving to the next day restores the retry budget
    (no permanent lockout when a concern is chronically unhooked)."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", True)

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _plan_result(_unhooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        # Day 1: initial + retry = 2
        asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"),
            _state_with_strong_concern(),
            next_exam_in_days=20, day=1,
            all_profiles=_all_profiles(),
        ))
        # Day 2: fresh budget, initial + retry = 2 more
        asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"),
            _state_with_strong_concern(),
            next_exam_in_days=19, day=2,
            all_profiles=_all_profiles(),
        ))
    assert call_count == 4


def test_intensity_6_not_audited(monkeypatch):
    """PR6: threshold is >=7. An intensity-6 concern should not trigger
    audit / retry."""
    _reset_audit_budget()
    monkeypatch.setattr(settings, "daily_plan_audit_retry", True)
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="普通焦虑", id="sixsix",
            topic="家庭压力", related_people=["父亲"], intensity=6,
            last_new_info_day=3,
        ),
    ])

    call_count = 0
    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _plan_result(_unhooked_intentions())

    with patch("sim.agent.daily_plan.structured_call", side_effect=fake_call), \
         patch("sim.agent.daily_plan.log_llm_call"):
        asyncio.run(generate_daily_plan(
            "a", _storage_mock(), _student("a", "张伟"), state,
            next_exam_in_days=20, day=1,
            all_profiles=_all_profiles(),
        ))
    assert call_count == 1  # no retry
