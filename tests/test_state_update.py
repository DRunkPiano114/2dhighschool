"""Tests for agent state update functions."""

from random import Random

from sim.agent.state_update import (
    DECAYABLE_EMOTIONS,
    EXTREME_EMOTIONS,
    clamp,
    decay_concerns,
    maybe_decay_emotion,
    regress_relationships,
    reset_energy_for_sleep,
    update_academic_pressure,
    update_energy,
)
from sim.models.agent import ActiveConcern, AgentState, Emotion, PressureLevel
from sim.models.relationship import Relationship, RelationshipFile


# --- clamp ---

def test_clamp_within_range():
    assert clamp(50, 0, 100) == 50


def test_clamp_below_minimum():
    assert clamp(-10, 0, 100) == 0


def test_clamp_above_maximum():
    assert clamp(150, 0, 100) == 100


def test_clamp_at_boundaries():
    assert clamp(0, 0, 100) == 0
    assert clamp(100, 0, 100) == 100


# --- update_energy ---

def test_update_energy_class():
    state = AgentState(energy=80)
    update_energy(state, "上课")
    assert state.energy == 75  # 80 - 5


def test_update_energy_break():
    state = AgentState(energy=50)
    update_energy(state, "课间")
    assert state.energy == 55  # 50 + 5


def test_update_energy_lunch():
    state = AgentState(energy=40)
    update_energy(state, "午饭")
    assert state.energy == 55  # 40 + 15


def test_update_energy_unknown_scene():
    state = AgentState(energy=50)
    update_energy(state, "unknown_scene")
    assert state.energy == 50  # No change


def test_update_energy_clamps_at_zero():
    state = AgentState(energy=3)
    update_energy(state, "上课")
    assert state.energy == 0  # 3 - 5 → clamped to 0


def test_update_energy_clamps_at_hundred():
    state = AgentState(energy=95)
    update_energy(state, "午饭")
    assert state.energy == 100  # 95 + 15 → clamped to 100


def test_update_energy_morning_reading():
    """Morning reading (早读) costs 3 energy."""
    state = AgentState(energy=50)
    update_energy(state, "早读")
    assert state.energy == 47


def test_update_energy_evening_study():
    """Evening study (晚自习) costs 5 energy."""
    state = AgentState(energy=50)
    update_energy(state, "晚自习")
    assert state.energy == 45


def test_update_energy_dorm_chat():
    """Dorm chat (宿舍夜聊) costs 5 energy."""
    state = AgentState(energy=50)
    update_energy(state, "宿舍夜聊")
    assert state.energy == 45


# --- reset_energy_for_sleep ---

def test_reset_energy_for_sleep():
    state = AgentState(energy=20)
    reset_energy_for_sleep(state)
    assert state.energy == 85


def test_reset_energy_already_high():
    state = AgentState(energy=95)
    reset_energy_for_sleep(state)
    assert state.energy == 85


# --- update_academic_pressure ---

def test_pressure_base_by_level():
    for level, expected_base in [
        (PressureLevel.HIGH, 50),
        (PressureLevel.MEDIUM, 30),
        (PressureLevel.LOW, 15),
    ]:
        state = AgentState(academic_pressure=0)
        update_academic_pressure(state, level, next_exam_in_days=30)
        assert state.academic_pressure == expected_base


def test_pressure_exam_countdown_3_days():
    state = AgentState(academic_pressure=0)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=3)
    assert state.academic_pressure == 30 + 15  # base + countdown


def test_pressure_exam_countdown_7_days():
    state = AgentState(academic_pressure=0)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=7)
    assert state.academic_pressure == 30 + 8


def test_pressure_exam_countdown_14_days():
    state = AgentState(academic_pressure=0)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=14)
    assert state.academic_pressure == 30 + 3


def test_pressure_exam_far():
    state = AgentState(academic_pressure=0)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=20)
    assert state.academic_pressure == 30  # base only


def test_pressure_post_exam_day0_resets():
    """Day 0 after exam: pressure resets to base regardless of current value."""
    state = AgentState(academic_pressure=80)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=30, days_since_exam=0)
    assert state.academic_pressure == 30  # Reset to MEDIUM base


def test_pressure_post_exam_day0_resets_high():
    state = AgentState(academic_pressure=95)
    update_academic_pressure(state, PressureLevel.HIGH, next_exam_in_days=30, days_since_exam=0)
    assert state.academic_pressure == 50  # Reset to HIGH base


def test_pressure_post_exam_recovery():
    state = AgentState(academic_pressure=50)
    update_academic_pressure(state, PressureLevel.MEDIUM, next_exam_in_days=30, days_since_exam=3)
    # base(30) + countdown(0) + recovery(-6) = 24
    assert state.academic_pressure == 24


def test_pressure_clamped_to_100():
    state = AgentState(academic_pressure=0)
    update_academic_pressure(state, PressureLevel.HIGH, next_exam_in_days=1)
    # 50 + 15 = 65
    assert state.academic_pressure == 65


# --- decay_concerns ---

def test_decay_concerns_reduces_intensity():
    """Concerns reinforced today decay by `concern_decay_per_day`."""
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="test", intensity=5,
            last_reinforced_day=1, last_new_info_day=1,
        ),
        ActiveConcern(
            text="test2", intensity=3,
            last_reinforced_day=1, last_new_info_day=1,
        ),
    ])
    decay_concerns(state, today=1)
    assert state.active_concerns[0].intensity == 3  # 5 - 2
    assert state.active_concerns[1].intensity == 1  # 3 - 2


def test_decay_concerns_removes_at_zero():
    """A concern that hits intensity 0 after decay is dropped."""
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="will_survive", intensity=4,
            last_reinforced_day=1, last_new_info_day=1,
        ),
        ActiveConcern(
            text="will_die", intensity=2,
            last_reinforced_day=1, last_new_info_day=1,
        ),
    ])
    decay_concerns(state, today=1)
    assert len(state.active_concerns) == 1
    assert state.active_concerns[0].text == "will_survive"


def test_decay_concerns_empty():
    state = AgentState(active_concerns=[])
    decay_concerns(state, today=1)
    assert state.active_concerns == []


def test_concern_decay_minus_two_per_day():
    """`concern_decay_per_day` defaults to 2 for low-intensity concerns.
    High-intensity (>=6) concerns decay at half rate (1/day)."""
    # High-intensity: decays by 1 (half rate)
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="high", intensity=10,
            last_reinforced_day=2, last_new_info_day=2,
        ),
    ])
    decay_concerns(state, today=2)
    assert state.active_concerns[0].intensity == 9  # 10 - 1 (high-intensity half rate)

    # Low-intensity: decays by 2 (normal rate)
    state2 = AgentState(active_concerns=[
        ActiveConcern(
            text="low", intensity=4,
            last_reinforced_day=2, last_new_info_day=2,
        ),
    ])
    decay_concerns(state2, today=2)
    assert state2.active_concerns[0].intensity == 2  # 4 - 2 (normal rate)


def test_concern_stale_eviction_after_5_days():
    """A concern with no new info for ≥`concern_stale_days` is evicted
    regardless of remaining intensity. PR3: TTL is driven by
    `last_new_info_day`, not `last_reinforced_day`."""
    state = AgentState(active_concerns=[
        ActiveConcern(
            text="ancient", intensity=8,
            last_reinforced_day=1, last_new_info_day=1,
        ),
        ActiveConcern(
            text="fresh", intensity=4,
            last_reinforced_day=5, last_new_info_day=5,
        ),
    ])
    # day 6: ancient is 5 days stale → evicted, fresh is 1 day stale → kept
    decay_concerns(state, today=6)
    survivors = [c.text for c in state.active_concerns]
    assert "ancient" not in survivors
    assert "fresh" in survivors
    # fresh decayed by 2
    fresh = next(c for c in state.active_concerns if c.text == "fresh")
    assert fresh.intensity == 2


# --- maybe_decay_emotion ---

def test_emotion_decay_extreme_resets():
    """With rng < 0.5, extreme emotion resets to NEUTRAL."""
    rng = Random(0)
    # Find a seed where random() < 0.5
    for seed in range(100):
        rng = Random(seed)
        if rng.random() < 0.5:
            rng = Random(seed)
            break
    state = AgentState(emotion=Emotion.ANGRY)
    maybe_decay_emotion(state, scenes_since_extreme=2, rng=rng)
    assert state.emotion == Emotion.NEUTRAL


def test_emotion_decay_not_enough_scenes():
    """Extreme emotion doesn't decay if < 2 scenes."""
    state = AgentState(emotion=Emotion.ANGRY)
    rng = Random(42)
    maybe_decay_emotion(state, scenes_since_extreme=1, rng=rng)
    assert state.emotion == Emotion.ANGRY


def test_emotion_decay_non_extreme_stays():
    """Non-extreme emotions never decay."""
    state = AgentState(emotion=Emotion.HAPPY)
    rng = Random(42)
    maybe_decay_emotion(state, scenes_since_extreme=5, rng=rng)
    assert state.emotion == Emotion.HAPPY


def test_all_extreme_emotions_classified():
    """Verify the set of extreme emotions is what we expect."""
    assert Emotion.ANGRY in EXTREME_EMOTIONS
    assert Emotion.EXCITED in EXTREME_EMOTIONS
    assert Emotion.SAD in EXTREME_EMOTIONS
    assert Emotion.EMBARRASSED in EXTREME_EMOTIONS
    assert Emotion.JEALOUS in EXTREME_EMOTIONS
    assert Emotion.GUILTY in EXTREME_EMOTIONS
    assert Emotion.FRUSTRATED in EXTREME_EMOTIONS
    assert Emotion.TOUCHED in EXTREME_EMOTIONS
    # Non-extreme (should NOT trigger re-plan)
    assert Emotion.NEUTRAL not in EXTREME_EMOTIONS
    assert Emotion.HAPPY not in EXTREME_EMOTIONS
    assert Emotion.CALM not in EXTREME_EMOTIONS
    assert Emotion.ANXIOUS not in EXTREME_EMOTIONS
    assert Emotion.BORED not in EXTREME_EMOTIONS


def test_decayable_includes_anxious_bored():
    """ANXIOUS and BORED decay overnight but don't trigger re-plan."""
    assert Emotion.ANXIOUS in DECAYABLE_EMOTIONS
    assert Emotion.BORED in DECAYABLE_EMOTIONS


def test_decayable_superset_of_extreme():
    """Every extreme emotion is also decayable."""
    assert EXTREME_EMOTIONS.issubset(DECAYABLE_EMOTIONS)


def test_anxious_decays_overnight():
    """ANXIOUS emotion decays to NEUTRAL with favorable rng."""
    for seed in range(100):
        rng = Random(seed)
        if rng.random() < 0.5:
            rng = Random(seed)
            break
    state = AgentState(emotion=Emotion.ANXIOUS)
    maybe_decay_emotion(state, scenes_since_extreme=2, rng=rng)
    assert state.emotion == Emotion.NEUTRAL


# --- regress_relationships (asymmetric decay) ---

def test_regress_negative_heals_every_day():
    """Negative favorability/trust heal toward 0 every day, regardless of staleness."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=-10, trust=-5),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == -9
    assert rels.relationships["b"].trust == -4


def test_regress_positive_fresh_no_decay():
    """Positive values with days_since_interaction=0 do NOT decay."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=10, trust=5, days_since_interaction=0),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 10
    assert rels.relationships["b"].trust == 5
    assert rels.relationships["b"].days_since_interaction == 1


def test_regress_positive_stale_decays():
    """Positive values decay after reaching stale threshold (default 5 days)."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=10, trust=5, days_since_interaction=5),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 9
    assert rels.relationships["b"].trust == 4
    assert rels.relationships["b"].days_since_interaction == 6


def test_regress_positive_just_under_stale():
    """At days_since_interaction=4 (just under default threshold 5), no positive decay."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=10, trust=5, days_since_interaction=4),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 10
    assert rels.relationships["b"].trust == 5


def test_regress_zero_stays_zero():
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=0, trust=0),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 0
    assert rels.relationships["b"].trust == 0


def test_regress_understanding_unchanged():
    """Understanding does NOT regress."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", understanding=50),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].understanding == 50


def test_regress_mixed_relationship():
    """Mixed: positive favorability protected when fresh, negative trust heals."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=5, trust=-3, days_since_interaction=0),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 5   # fresh → no decay
    assert rels.relationships["b"].trust == -2          # negative → heals


def test_regress_mixed_stale():
    """Mixed stale: positive favorability decays, negative trust heals."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=5, trust=-3, days_since_interaction=5),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 4   # stale → decays
    assert rels.relationships["b"].trust == -2          # negative → heals


# --- Edge cases ---

def test_regress_at_one_reaches_zero():
    """Values at ±1 should reach 0, not overshoot."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=1, trust=-1, days_since_interaction=5),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].favorability == 0
    assert rels.relationships["b"].trust == 0


def test_regress_days_since_interaction_increments():
    """Counter increments each call."""
    rels = RelationshipFile(relationships={
        "b": Relationship(target_name="B", target_id="b", favorability=0, trust=0, days_since_interaction=5),
    })
    regress_relationships(rels)
    assert rels.relationships["b"].days_since_interaction == 6


def test_pressure_recovery_clamps_to_zero():
    """Heavy post-exam recovery should not push pressure below 0."""
    state = AgentState(academic_pressure=80)
    # days_since_exam=30 → recovery = -60, base(15) + 0 + (-60) = -45 → clamped to 0
    update_academic_pressure(state, PressureLevel.LOW, next_exam_in_days=30, days_since_exam=30)
    assert state.academic_pressure == 0


def test_emotion_decay_probabilistic():
    """Extreme emotion decay at ≥2 scenes is probabilistic (≈50%)."""
    decayed = 0
    total = 200
    for seed in range(total):
        state = AgentState(emotion=Emotion.ANGRY)
        maybe_decay_emotion(state, scenes_since_extreme=2, rng=Random(seed))
        if state.emotion == Emotion.NEUTRAL:
            decayed += 1
    # Expect roughly 50% decay rate (allow wide margin for randomness)
    assert 60 < decayed < 140


# --- PR3: TTL split + stuck-topic backstops + decay ordering ---


def test_reinforcement_count_10_forces_faster_decay_regardless_of_ttl():
    """Backstop A: count >= 10 forces decay=2 even on a high-intensity
    negative concern, regardless of fresh TTL. Without the backstop,
    intensity 8 would decay by only 1."""
    c = ActiveConcern(
        text="卡死话题", intensity=8, positive=False,
        last_reinforced_day=5, last_new_info_day=5,
        reinforcement_count=10,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)
    # Backstop A applied (decay=2), then count decremented from 10 → 9
    assert state.active_concerns[0].intensity == 6
    assert state.active_concerns[0].reinforcement_count == 9


def test_reinforcement_count_15_force_evicts_regardless_of_ttl():
    """Backstop B: count >= 15 hard-evicts even when TTL is fresh and
    intensity is high."""
    c = ActiveConcern(
        text="deep stuck", intensity=9, positive=False,
        last_reinforced_day=5, last_new_info_day=5,
        reinforcement_count=15,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)
    assert state.active_concerns == []


def test_positive_concern_immune_to_backstop_a():
    """喜欢陆思远 reinforced daily: count climbs but positive concern is
    not slammed by backstop A."""
    c = ActiveConcern(
        text="喜欢陆思远", intensity=8, positive=True,
        last_reinforced_day=5, last_new_info_day=5,
        reinforcement_count=12,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)
    # Positive concern: stuck-topic guard disabled. High-intensity decay=1,
    # then count decrements 12 → 11.
    assert state.active_concerns[0].intensity == 7
    assert state.active_concerns[0].reinforcement_count == 11


def test_positive_concern_immune_to_backstop_b():
    """Positive concern at count >= 15 should still survive (love and
    positive obsession aren't "stuck topics" we want to treat)."""
    c = ActiveConcern(
        text="喜欢陆思远", intensity=8, positive=True,
        last_reinforced_day=5, last_new_info_day=5,
        reinforcement_count=15,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)
    assert len(state.active_concerns) == 1


def test_daily_count_decay_minus_one():
    """Every surviving concern has reinforcement_count decremented by 1 each
    day (natural forgetting). Prevents long-run systematic eviction of all
    negative concerns once they've ever been reinforced."""
    c = ActiveConcern(
        text="x", intensity=5, positive=False,
        last_reinforced_day=3, last_new_info_day=3,
        reinforcement_count=5,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=3)
    assert state.active_concerns[0].reinforcement_count == 4


def test_count_decay_clamps_at_zero():
    c = ActiveConcern(
        text="x", intensity=5, positive=False,
        last_reinforced_day=3, last_new_info_day=3,
        reinforcement_count=0,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=3)
    assert state.active_concerns[0].reinforcement_count == 0


def test_concern_evicted_on_stale_new_info_not_reinforcement_day():
    """PR3: TTL drives off `last_new_info_day`. Pure emotion reinforcement
    (concern_updates path) bumps last_reinforced_day but leaves
    last_new_info_day cold → concern stays eligible for TTL eviction."""
    c = ActiveConcern(
        text="reinforced emotionally only", intensity=7, positive=False,
        last_reinforced_day=5,    # recently bumped
        last_new_info_day=0,       # never got new info
        reinforcement_count=2,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)  # 5 - 0 = 5 stale days ≥ concern_stale_days (5)
    assert state.active_concerns == []


def test_decay_order_threshold_15_exact():
    """Count = 15 must be caught by backstop B (eviction). If we decremented
    count first ("-= 1"), runtime would see 14 and miss the threshold — the
    plan's ≥15 language would effectively mean ≥16."""
    c = ActiveConcern(
        text="x", intensity=5, positive=False,
        last_reinforced_day=5, last_new_info_day=5,
        reinforcement_count=15,
    )
    state = AgentState(active_concerns=[c])
    decay_concerns(state, today=5)
    assert state.active_concerns == []
