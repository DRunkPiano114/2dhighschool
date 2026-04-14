import pytest
from pydantic import ValidationError

from sim.models.agent import (
    Academics,
    ActiveConcern,
    AgentProfile,
    BehavioralAnchors,
    Emotion,
    FamilyBackground,
    Gender,
    OverallRank,
    PressureLevel,
    Role,
)
from sim.models.dialogue import (
    ActionType,
    AgentConcernCandidate,
    AgentRelChange,
    NewEventCandidate,
    PerceptionOutput,
)


def test_perception_output_required_fields():
    out = PerceptionOutput(
        observation="看到有人在说话",
        inner_thought="没什么意思",
        emotion=Emotion.NEUTRAL,
        action_type=ActionType.OBSERVE,
        urgency=3,
    )
    assert out.action_content is None
    assert out.action_target is None
    assert out.is_disruptive is False


def test_urgency_range_lower_bound():
    with pytest.raises(ValidationError):
        PerceptionOutput(
            observation="x",
            inner_thought="x",
            emotion=Emotion.NEUTRAL,
            action_type=ActionType.OBSERVE,
            urgency=0,
        )


def test_urgency_range_upper_bound():
    with pytest.raises(ValidationError):
        PerceptionOutput(
            observation="x",
            inner_thought="x",
            emotion=Emotion.NEUTRAL,
            action_type=ActionType.OBSERVE,
            urgency=11,
        )


def test_urgency_valid_boundaries():
    out1 = PerceptionOutput(
        observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
        action_type=ActionType.OBSERVE, urgency=1,
    )
    out10 = PerceptionOutput(
        observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
        action_type=ActionType.OBSERVE, urgency=10,
    )
    assert out1.urgency == 1
    assert out10.urgency == 10


def test_is_disruptive_default():
    out = PerceptionOutput(
        observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
        action_type=ActionType.NON_VERBAL, urgency=5,
        action_content="低头写字",
    )
    assert out.is_disruptive is False


def test_action_types():
    assert ActionType.SPEAK == "speak"
    assert ActionType.NON_VERBAL == "non_verbal"
    assert ActionType.OBSERVE == "observe"
    assert ActionType.EXIT == "exit"


# --- ConcernTopic Literal validation ---


def test_concern_topic_literal_valid_values():
    """All 10 enum members should be accepted by Pydantic."""
    for topic in [
        "学业焦虑", "家庭压力", "人际矛盾", "恋爱", "自我认同",
        "未来规划", "健康", "兴趣爱好", "期待的事", "其他",
    ]:
        c = ActiveConcern(text="x", topic=topic)  # type: ignore[arg-type]
        assert c.topic == topic


def test_concern_topic_literal_validation_rejects_unknown():
    """A free-text topic the LLM might invent ('英语学习') must be rejected
    so the dedup buckets stay coherent."""
    with pytest.raises(ValidationError):
        ActiveConcern(text="x", topic="英语学习")  # type: ignore[arg-type]


def test_concern_topic_literal_default():
    """Default topic is '其他'."""
    c = ActiveConcern(text="x")
    assert c.topic == "其他"


def test_agent_concern_candidate_topic_default():
    """LLM-output candidate model also defaults to '其他'."""
    c = AgentConcernCandidate(text="x")
    assert c.topic == "其他"


def test_agent_concern_candidate_topic_positive_bucket():
    """LLM can choose a positive bucket like '兴趣爱好'."""
    c = AgentConcernCandidate(text="x", topic="兴趣爱好", positive=True)  # type: ignore[arg-type]
    assert c.topic == "兴趣爱好"
    assert c.positive is True


# --- NewEventCandidate.cite_ticks ---


def test_new_event_candidate_cite_ticks_default_empty():
    c = NewEventCandidate(text="x")
    assert c.cite_ticks == []


def test_new_event_candidate_cite_ticks_serialization():
    c = NewEventCandidate(text="x", cite_ticks=[1, 3, 5])
    dump = c.model_dump()
    assert dump["cite_ticks"] == [1, 3, 5]
    # Round trip
    restored = NewEventCandidate.model_validate(dump)
    assert restored.cite_ticks == [1, 3, 5]


# --- BehavioralAnchors (Fix 5) ---


def test_behavioral_anchors_default_empty():
    """New profile without explicit anchors gets empty lists."""
    profile = AgentProfile(
        agent_id="test", name="测试", gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )
    assert profile.behavioral_anchors.must_do == []
    assert profile.behavioral_anchors.never_do == []
    assert profile.behavioral_anchors.speech_patterns == []


def test_behavioral_anchors_max_length():
    """Exceeding max_length=5 for must_do should be rejected by Pydantic."""
    with pytest.raises(ValidationError):
        BehavioralAnchors(must_do=["a", "b", "c", "d", "e", "f"])


def test_behavioral_anchors_speech_patterns_max_length():
    """Exceeding max_length=6 for speech_patterns should be rejected."""
    with pytest.raises(ValidationError):
        BehavioralAnchors(speech_patterns=["a", "b", "c", "d", "e", "f", "g"])


# --- AgentRelChange.direct_interaction (Fix 5) ---


def test_agent_rel_change_direct_interaction_default_false():
    """Unmarked LLM output defaults to observer (not direct)."""
    change = AgentRelChange(to_agent="张伟")
    assert change.direct_interaction is False


def test_agent_rel_change_direct_interaction_explicit_true():
    change = AgentRelChange(to_agent="张伟", direct_interaction=True)
    assert change.direct_interaction is True


# --- ActiveConcern: id + new fields (PR1) ---


def test_active_concern_auto_generates_id():
    c = ActiveConcern(text="x")
    assert isinstance(c.id, str)
    assert len(c.id) == 6  # 3 bytes → 6 hex chars
    # lower-case hex
    assert all(ch in "0123456789abcdef" for ch in c.id)


def test_active_concern_distinct_default_ids():
    a = ActiveConcern(text="x")
    b = ActiveConcern(text="x")
    assert a.id != b.id  # factory runs per instance


def test_active_concern_id_persists_across_load():
    c = ActiveConcern(text="x")
    original = c.id
    roundtrip = ActiveConcern.model_validate(c.model_dump())
    assert roundtrip.id == original


def test_active_concern_load_legacy_missing_id():
    """A serialized concern without an id (pre-migration payload) should
    load cleanly and auto-generate one on demand."""
    legacy = {"text": "旧牵挂"}
    c = ActiveConcern.model_validate(legacy)
    assert c.id and len(c.id) == 6
    assert c.id_history == []
    assert c.last_new_info_day == 0
    assert c.reinforcement_count == 0


def test_active_concern_new_fields_defaults():
    c = ActiveConcern(text="x")
    assert c.id_history == []
    assert c.last_new_info_day == 0
    assert c.reinforcement_count == 0


def test_active_concern_id_history_max_length():
    """id_history caps at 5 entries."""
    with pytest.raises(ValidationError):
        ActiveConcern(text="x", id_history=["a", "b", "c", "d", "e", "f"])
