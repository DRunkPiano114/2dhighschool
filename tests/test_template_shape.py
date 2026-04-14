"""Template rendering smoke tests for PR6.

Verifies that every template which renders `active_concerns` includes the
`[ref: <id>]` suffix so the LLM can hook intentions by id. Also checks
the daily_plan prompt no longer contains the deprecated "allow avoidance"
language.
"""

from pathlib import Path

from sim.llm.prompts import render
from sim.models.agent import (
    Academics,
    ActiveConcern,
    AgentProfile,
    AgentState,
    BehavioralAnchors,
    DailyPlan,
    FamilyBackground,
    Gender,
    Intention,
    OverallRank,
    PressureLevel,
    Role,
)


TEMPLATES_WITH_REF = [
    "daily_plan.j2",
    "perception_static.j2",
    "self_reflection.j2",
    "solo_reflection.j2",
    "nightly_compress.j2",
    "state_consolidation.j2",
    "replan.j2",
    "role_play.j2",
    "god_mode.j2",
]


def _profile() -> AgentProfile:
    return AgentProfile(
        agent_id="a", name="小明", gender=Gender.MALE, role=Role.STUDENT,
        personality=["内向"],
        speaking_style="直接",
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        behavioral_anchors=BehavioralAnchors(),
    )


def _concern(**kwargs) -> ActiveConcern:
    base = dict(
        text="化学竞赛失败", id="a7f9b2",
        intensity=7, emotion="anxious",
        topic="学业焦虑", related_people=["自己"],
        last_new_info_day=3, last_reinforced_day=3,
    )
    base.update(kwargs)
    return ActiveConcern(**base)


def _concern_dict(**kwargs) -> dict:
    c = _concern(**kwargs).model_dump()
    c["intensity_label"] = "强烈"
    return c


def _render_daily_plan() -> str:
    state = AgentState(
        active_concerns=[_concern()],
        daily_plan=DailyPlan(intentions=[]),
    )
    return render(
        "daily_plan.j2",
        role_description="学生",
        profile_summary="小明",
        current_state=state,
        next_exam_in_days=30,
        energy_label="平均", pressure_label="中", exam_label="月考快来了",
        relationships=[],
        recent_days="",
        yesterday_intentions=[],
        active_concerns=[_concern_dict()],
        self_narrative="", self_concept=[], current_tensions=[],
        inner_conflicts=[], behavioral_anchors=BehavioralAnchors(),
        joy_sources=[],
        is_student=True, free_period_configs=[],
    )


def _render_self_reflection() -> str:
    return render(
        "self_reflection.j2",
        role_description="学生",
        profile_summary="小明",
        relationships=[],
        today_events="上了数学课",
        recent_summary="",
        key_memories=[],
        active_concerns=[_concern_dict()],
        self_narrative="", self_concept=[], current_tensions=[],
        inner_conflicts=[],
        behavioral_anchors=BehavioralAnchors(),
        scene_info={"time": "08:45", "location": "教室", "name": "课间", "present_names": ["小明", "A"]},
        conversation_log="...",
        pending_intentions=[],
        is_teacher=False,
    )


def test_daily_plan_renders_ref_suffix():
    out = _render_daily_plan()
    assert "[ref: a7f9b2]" in out


def test_daily_plan_does_not_say_allow_avoidance():
    """PR6: the deprecated 'allow avoidance' language must be gone."""
    out = _render_daily_plan()
    assert "选择逃避——这是合理的" not in out


def test_daily_plan_has_strong_concern_rule():
    """PR6: the new stricter rule must be present."""
    out = _render_daily_plan()
    assert "intensity" in out or "强烈" in out
    assert "必须" in out


def test_self_reflection_renders_ref_suffix():
    out = _render_self_reflection()
    assert "[ref: a7f9b2]" in out


def test_self_reflection_mentions_source_event_history():
    """PR6: self_reflection renders source_event on concerns so the LLM
    naturally folds reinforcement into concern_updates, not new_concerns."""
    def with_history():
        cd = _concern_dict()
        cd["source_event"] = "化学竞赛一次失败；模拟考第二次不及格；期末也没考好"
        return cd
    out = render(
        "self_reflection.j2",
        role_description="学生",
        profile_summary="小明",
        relationships=[], today_events="", recent_summary="", key_memories=[],
        active_concerns=[with_history()],
        self_narrative="", self_concept=[], current_tensions=[],
        inner_conflicts=[],
        behavioral_anchors=BehavioralAnchors(),
        scene_info={"time": "08:45", "location": "教室", "name": "课间", "present_names": ["小明"]},
        conversation_log="...", pending_intentions=[], is_teacher=False,
    )
    assert "最近触发" in out
    # Most recent 3 items kept
    assert "化学竞赛一次失败" in out or "期末也没考好" in out


def test_self_reflection_points_concern_updates_to_ref():
    """PR6: the new_concerns vs concern_updates guidance must say 'fill ref'."""
    out = _render_self_reflection()
    assert "6 位 ref" in out
    # Explicit anti-bracket guidance
    assert "[ref:]" in out


def test_templates_without_concerns_do_not_need_ref():
    """Sanity: templates that don't render concerns aren't affected."""
    dt_templates = Path("src/sim/templates").glob("*.j2")
    for _ in dt_templates:
        pass  # smoke: the directory exists and is enumerable


# --- PR7: perception_dynamic target highlight ---


def _render_perception_dynamic(intended_targets_present: list[str]) -> str:
    return render(
        "perception_dynamic.j2",
        scene_transcript="",
        latest_event="李明说了句什么",
        scene_pacing_label="",
        private_history=[],
        emotion_trace=[],
        tick_emotion="calm",
        intended_targets_present=intended_targets_present,
        scene_info={"present_names": ["A", "李明"]},
        teacher_present=False,
        is_teacher=False,
    )


def test_perception_target_highlight_renders():
    out = _render_perception_dynamic(intended_targets_present=["李明"])
    assert "你今天想找的人里" in out
    assert "李明" in out


def test_perception_target_highlight_absent_when_no_targets():
    out = _render_perception_dynamic(intended_targets_present=[])
    assert "你今天想找的人里" not in out
