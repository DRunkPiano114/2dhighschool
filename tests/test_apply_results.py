"""Tests for apply_results helpers: concern_match, add_concern,
trivial scene detection, relationship auto-extension, and event grounding."""

import random

from sim.agent.storage import WorldStorage, atomic_write_json
from sim.models.agent import (
    Academics,
    ActiveConcern,
    AgentProfile,
    AgentState,
    Emotion,
    FamilyBackground,
    Gender,
    OverallRank,
    PressureLevel,
    Role,
)
from sim.models.dialogue import (
    ActionType,
    AgentMemoryCandidate,
    AgentReflection,
    AgentRelChange,
    NarrativeExtraction,
    NewEventCandidate,
    PerceptionOutput,
)
from sim.models.event import EventQueue
from sim.models.relationship import Relationship, RelationshipFile
from sim.models.scene import Scene, SceneDensity
from sim.world.event_queue import EventQueueManager
from sim.interaction.apply_results import (
    add_concern,
    apply_scene_end_results,
    apply_trivial_scene_result,
    bump_concern_intensity,
    concern_lookup,
    concern_match,
    is_trivial_scene,
)


def _make_perception(
    action_type: ActionType = ActionType.OBSERVE,
    is_disruptive: bool = False,
    action_content: str | None = None,
) -> PerceptionOutput:
    return PerceptionOutput(
        observation="x",
        inner_thought="x",
        emotion=Emotion.NEUTRAL,
        action_type=action_type,
        action_content=action_content,
        urgency=3,
        is_disruptive=is_disruptive,
    )


# --- concern_match ---

def test_concern_match_exact():
    assert concern_match("被嘲笑", "被嘲笑") is True


def test_concern_match_substring_forward():
    assert concern_match("被江浩天当众嘲笑数学成绩", "当众嘲笑") is True


def test_concern_match_substring_reverse():
    assert concern_match("当众嘲笑", "被江浩天当众嘲笑数学成绩") is True


def test_concern_match_non_contiguous_fails():
    """Non-contiguous substring does NOT match."""
    assert concern_match("被江浩天当众嘲笑数学成绩", "被嘲笑") is False


def test_concern_match_no_match():
    assert concern_match("考试压力", "被嘲笑") is False


def test_concern_match_none():
    assert concern_match("anything", None) is False


def test_concern_match_empty_string():
    """Empty text_b is falsy → returns False."""
    assert concern_match("被嘲笑", "") is False


def test_concern_match_both_empty():
    """Both empty → text_b is falsy → returns False."""
    assert concern_match("", "") is False


# --- add_concern + topic-based dedup ---


def _make_concern(
    text: str = "test",
    intensity: int = 5,
    topic: str = "其他",
    people: list[str] | None = None,
    positive: bool = False,
    day: int = 1,
) -> ActiveConcern:
    return ActiveConcern(
        text=text,
        source_day=day,
        source_scene="课间",
        intensity=intensity,
        topic=topic,  # type: ignore[arg-type]
        related_people=people or [],
        positive=positive,
    )


def test_add_concern_merges_same_topic_with_people_overlap():
    """Two 学业焦虑 concerns with overlapping people merge: intensity bumps
    by 1, text and last_reinforced_day refresh."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(text="数学考砸", intensity=5, topic="学业焦虑", people=["张伟"])
    )
    new = _make_concern(text="物理也不行", intensity=4, topic="学业焦虑", people=["张伟", "李明"])
    add_concern(state, new, today=3)

    assert len(state.active_concerns) == 1
    merged = state.active_concerns[0]
    assert merged.topic == "学业焦虑"
    assert merged.intensity == 6  # 5 + 1
    assert merged.text == "物理也不行"
    assert merged.last_reinforced_day == 3


def test_other_topic_requires_exact_people_match():
    """For topic='其他' with non-empty people, only EXACT people set match merges."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(topic="其他", people=["张伟", "李明"])
    )
    # Same set, different order — should merge
    same_set = _make_concern(topic="其他", people=["李明", "张伟"])
    add_concern(state, same_set, today=2)
    assert len(state.active_concerns) == 1


def test_other_topic_different_people_not_merged():
    """For topic='其他', different (overlapping but not equal) people → not merged."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(topic="其他", people=["张伟"])
    )
    new = _make_concern(topic="其他", people=["张伟", "王芳"])
    add_concern(state, new, today=2)
    # Two separate entries
    assert len(state.active_concerns) == 2


def test_other_topic_empty_people_never_merges():
    """Two topic='其他' concerns with empty related_people → NEVER merge.
    Frankenstein guard: empty-people 其他 buckets are almost always unrelated
    things; merging produces a useless meta-concern."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(text="一些焦虑的事", topic="其他", people=[])
    )
    add_concern(
        state,
        _make_concern(text="另一件不相关的事", topic="其他", people=[]),
        today=2,
    )
    # Both concerns kept separately
    assert len(state.active_concerns) == 2


def test_add_concern_caps_intensity_at_6():
    """Default reflection-originated concerns are capped at
    `concern_autogen_max_intensity` (=6)."""
    state = AgentState()
    new = _make_concern(intensity=10, topic="学业焦虑", people=["张伟"])
    add_concern(state, new, today=1)
    assert state.active_concerns[0].intensity == 6


def test_add_concern_skip_cap_preserves_high_intensity():
    """High-priority paths (e.g. exam shock) pass skip_cap=True so the
    concern lands at full intensity."""
    state = AgentState()
    new = _make_concern(intensity=9, topic="学业焦虑", people=["张伟"])
    add_concern(state, new, today=1, skip_cap=True)
    assert state.active_concerns[0].intensity == 9


def test_add_concern_merge_ignores_high_intensity_claim_without_skip_cap():
    """Without skip_cap, a merge bumps existing by 1 — it cannot jump to a
    high LLM-claimed value, which would otherwise sneak past the cap."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(text="数学焦虑", intensity=5, topic="学业焦虑", people=["张伟"])
    )
    new = _make_concern(intensity=9, topic="学业焦虑", people=["张伟"])
    add_concern(state, new, today=2)

    assert state.active_concerns[0].intensity == 6


def test_add_concern_merge_does_not_demote_existing_high_intensity():
    """Reinforcement never reduces intensity. A regular reflection touching
    an existing intensity-9 concern bumps it to 10, not down to the cap."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(text="月考焦虑", intensity=9, topic="学业焦虑", people=["张伟"])
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    add_concern(state, new, today=2)

    assert state.active_concerns[0].intensity == 10


def test_add_concern_merge_skip_cap_jumps_to_max_plus_one():
    """With skip_cap=True the merge takes max(existing, new) + 1 — a
    follow-up shock can drive the floor up."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(intensity=5, topic="学业焦虑", people=["张伟"])
    )
    new = _make_concern(intensity=9, topic="学业焦虑", people=["张伟"])
    add_concern(state, new, today=2, skip_cap=True)

    assert state.active_concerns[0].intensity == 10


def test_positive_concern_uses_positive_topic_bucket():
    """A positive concern tagged with 兴趣爱好 / 期待的事 stays in that
    bucket — not merged with negative '其他' concerns."""
    state = AgentState()
    state.active_concerns.append(
        _make_concern(text="数学焦虑", intensity=5, topic="学业焦虑", people=["张伟"])
    )
    state.active_concerns.append(
        _make_concern(text="一件杂事", intensity=3, topic="其他", people=["李明"])
    )
    new = _make_concern(
        text="周末约朋友打球",
        intensity=4,
        topic="兴趣爱好",
        people=["王芳"],
        positive=True,
    )
    add_concern(state, new, today=2)
    # Three distinct entries; the positive one is in its own bucket
    assert len(state.active_concerns) == 3
    bucket = next(c for c in state.active_concerns if c.topic == "兴趣爱好")
    assert bucket.positive is True


def test_add_concern_merge_no_leading_delimiter_when_existing_empty():
    """Merging into a concern with empty source_event must not produce
    a leading '；'."""
    state = AgentState()
    state.active_concerns.append(
        ActiveConcern(
            text="数学焦虑",
            source_event="",  # default empty (e.g. concern from compression path)
            source_scene="课间",
            source_day=1,
            intensity=5,
            topic="学业焦虑",
            related_people=["张伟"],
        )
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    new.source_event = "数学小测又不及格"
    add_concern(state, new, today=2)

    merged = state.active_concerns[0]
    assert merged.source_event == "数学小测又不及格"
    assert not merged.source_event.startswith("；")


def test_add_concern_merge_no_trailing_delimiter_when_new_empty():
    """Merging an empty source_event must not produce a trailing '；'."""
    state = AgentState()
    state.active_concerns.append(
        ActiveConcern(
            text="数学焦虑",
            source_event="数学小测又不及格",
            source_scene="课间",
            source_day=1,
            intensity=5,
            topic="学业焦虑",
            related_people=["张伟"],
        )
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    new.source_event = ""
    add_concern(state, new, today=2)

    merged = state.active_concerns[0]
    assert merged.source_event == "数学小测又不及格"
    assert not merged.source_event.endswith("；")


def test_add_concern_merge_concatenates_with_delimiter_when_both_present():
    """Both sides non-empty → 'a；b'."""
    state = AgentState()
    state.active_concerns.append(
        ActiveConcern(
            text="数学焦虑",
            source_event="月考分数下滑",
            source_scene="课间",
            source_day=1,
            intensity=5,
            topic="学业焦虑",
            related_people=["张伟"],
        )
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    new.source_event = "数学小测又不及格"
    add_concern(state, new, today=2)

    merged = state.active_concerns[0]
    assert merged.source_event == "月考分数下滑；数学小测又不及格"


def test_add_concern_merge_source_event_truncates_oldest_when_over_cap():
    """When the concatenated source_event exceeds 500 chars, truncation
    must preserve the MOST RECENT trigger and drop the oldest prefix.
    Design intent: readers of `source_event` want to see 'what set this
    concern off lately', not 'the first thing that ever triggered it' —
    the latter is valuable for lore but the former is what the LLM and
    human reviewers consume tick-to-tick. Slicing with [:500] (keep head)
    would do the opposite and silently discard every reinforcement after
    the buffer filled."""
    state = AgentState()
    long_existing = "旧" * 499  # 499 chars, almost at the 500 cap
    state.active_concerns.append(
        ActiveConcern(
            text="学业焦虑",
            source_event=long_existing,
            source_scene="课间",
            source_day=1,
            intensity=5,
            topic="学业焦虑",
            related_people=["张伟"],
        )
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    new_trigger = "数学小测又不及格"  # fresh 8-char trigger
    new.source_event = new_trigger
    add_concern(state, new, today=2)

    merged = state.active_concerns[0]
    # Cap is respected.
    assert len(merged.source_event) == 500
    # Newest trigger is fully preserved at the tail.
    assert merged.source_event.endswith(new_trigger)
    # Arithmetic: pre-truncation length = 499 (old) + 1 (delimiter "；") +
    # len(new_trigger) = 508. Slicing [-500:] drops 508 - 500 = 8 chars
    # from the HEAD (oldest), so 499 - 8 = 491 "旧" characters survive.
    # The delimiter and the 8-char new trigger are untouched at the tail.
    dropped_from_head = (499 + 1 + len(new_trigger)) - 500
    assert merged.source_event.count("旧") == 499 - dropped_from_head
    # And the full string is exactly that many "旧" + delimiter + new.
    assert merged.source_event == (
        "旧" * (499 - dropped_from_head) + "；" + new_trigger
    )


def test_add_concern_merge_source_event_keeps_chronological_order():
    """Even when truncation kicks in, surviving content stays in 'oldest
    first, newest last' order so a reader scans the log naturally."""
    state = AgentState()
    state.active_concerns.append(
        ActiveConcern(
            text="学业焦虑",
            source_event="事件A；事件B；事件C",
            source_scene="课间",
            source_day=1,
            intensity=5,
            topic="学业焦虑",
            related_people=["张伟"],
        )
    )
    new = _make_concern(intensity=4, topic="学业焦虑", people=["张伟"])
    new.source_event = "事件D"
    add_concern(state, new, today=2)

    merged = state.active_concerns[0]
    # Well under 500 chars so no truncation here — just confirms the
    # append order of old-then-new, which is what [-500:] preserves when
    # the cap eventually triggers.
    assert merged.source_event == "事件A；事件B；事件C；事件D"


def test_add_concern_evicts_lowest_intensity():
    """When at max_active_concerns, a higher-intensity new concern evicts
    the lowest one."""
    state = AgentState()
    for i in range(4):  # max_active_concerns is 4
        state.active_concerns.append(
            _make_concern(text=f"c{i}", intensity=2 + i, topic="其他", people=[f"p{i}"])
        )
    # All four occupy slots, lowest intensity = 2
    new = _make_concern(text="newer", intensity=8, topic="学业焦虑", people=["zz"])
    add_concern(state, new, today=2)  # cap brings 8 → 6
    assert len(state.active_concerns) == 4
    # The intensity-2 concern was evicted
    intensities = sorted(c.intensity for c in state.active_concerns)
    assert 2 not in intensities
    assert 6 in intensities  # the new one (capped at 6)


# --- is_trivial_scene ---


def _make_tick(
    tick: int = 0,
    speech=None,
    actions=None,
    env_event: str | None = None,
) -> dict:
    return {
        "tick": tick,
        "agent_outputs": {},
        "resolved_speech": speech,
        "resolved_actions": actions or [],
        "environmental_event": env_event,
        "exits": [],
    }


def test_is_trivial_scene_empty():
    """Empty turn_records → trivial (defensive guard)."""
    assert is_trivial_scene([]) is True


def test_is_trivial_scene_no_speech_no_env():
    """No speech, no environmental events anywhere → trivial."""
    ticks = [
        _make_tick(tick=0, actions=[("a", _make_perception(ActionType.OBSERVE))]),
        _make_tick(tick=1, actions=[("b", _make_perception(ActionType.OBSERVE))]),
        _make_tick(tick=2, actions=[("a", _make_perception(ActionType.OBSERVE))]),
    ]
    assert is_trivial_scene(ticks) is True


def test_is_trivial_scene_few_observe_only_ticks():
    """≤2 ticks with only observe actions → trivial."""
    ticks = [
        _make_tick(tick=0, actions=[("a", _make_perception(ActionType.OBSERVE))]),
        _make_tick(tick=1, actions=[("b", _make_perception(ActionType.OBSERVE))]),
    ]
    assert is_trivial_scene(ticks) is True


def test_is_trivial_scene_normal_with_speech():
    """A regular scene with multiple speaking ticks is not trivial."""
    speech = ("a", _make_perception(ActionType.SPEAK, action_content="嘿"))
    ticks = [
        _make_tick(tick=0, speech=speech),
        _make_tick(tick=1, speech=speech),
        _make_tick(tick=2, speech=speech),
    ]
    assert is_trivial_scene(ticks) is False


def test_is_trivial_scene_disruptive_action_in_long_scene():
    """In a >2-tick scene, a disruptive non_verbal that production routes
    through environmental_event is NOT trivial."""
    disruptive = ("a", _make_perception(
        ActionType.NON_VERBAL,
        is_disruptive=True,
        action_content="拍桌子",
    ))
    # Production: resolve_tick sets environmental_event when is_disruptive=True
    ticks = [
        _make_tick(tick=0, actions=[disruptive], env_event="【动作】张伟: 拍桌子"),
        _make_tick(tick=1),
        _make_tick(tick=2),
    ]
    assert is_trivial_scene(ticks) is False


def test_is_trivial_scene_short_with_only_env_is_still_trivial():
    """≤2 ticks with env but no speech and no disruptive action → trivial.
    Background environment events alone don't justify a reflection LLM call."""
    ticks = [
        _make_tick(tick=0, env_event="老师走进来"),
    ]
    assert is_trivial_scene(ticks) is True


# --- apply_trivial_scene_result ---


def _setup_world(tmp_path):
    agents_dir = tmp_path / "agents"
    world_dir = tmp_path / "world"
    agents_dir.mkdir()
    world_dir.mkdir()
    return WorldStorage(agents_dir=agents_dir, world_dir=world_dir), agents_dir


def _setup_agent(
    agents_dir,
    aid: str,
    name: str = "张伟",
    role: Role = Role.STUDENT,
) -> AgentProfile:
    profile = AgentProfile(
        agent_id=aid, name=name, gender=Gender.MALE, role=role,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )
    agent_dir = agents_dir / aid
    agent_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(agent_dir / "profile.json", profile.model_dump())
    state = AgentState(
        emotion=Emotion.HAPPY,
        active_concerns=[ActiveConcern(text="existing", intensity=5)],
    )
    atomic_write_json(agent_dir / "state.json", state.model_dump())
    rels = RelationshipFile(relationships={
        "other": Relationship(target_name="李明", target_id="other", favorability=10),
    })
    atomic_write_json(agent_dir / "relationships.json", rels.model_dump())
    return profile


def _make_scene(
    scene_index: int = 0,
    day: int = 1,
    time: str = "08:45",
    name: str = "课间",
    location: str = "教室",
    agent_ids: list[str] | None = None,
) -> Scene:
    return Scene(
        scene_index=scene_index, day=day, time=time, name=name,
        location=location, density=SceneDensity.LOW,
        agent_ids=agent_ids or ["a"],
    )


def test_trivial_scene_no_state_change(tmp_path):
    """apply_trivial_scene_result must NOT touch emotion / concerns / memories / relationships."""
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent(agents_dir, "a")
    profiles = {"a": profile}
    scene = _make_scene()

    apply_trivial_scene_result(["a"], world, scene, day=1, profiles=profiles)

    state = world.get_agent("a").load_state()
    rels = world.get_agent("a").load_relationships()
    km = world.get_agent("a").load_key_memories()

    # State preserved
    assert state.emotion == Emotion.HAPPY
    assert len(state.active_concerns) == 1
    assert state.active_concerns[0].text == "existing"
    assert state.active_concerns[0].intensity == 5

    # Relationships preserved
    assert rels.relationships["other"].favorability == 10

    # No new key memories
    assert len(km.memories) == 0

    # today.md got the placeholder entry
    today = world.get_agent("a").read_today_md()
    assert "课间" in today
    assert "没有特别发生什么" in today


# --- relationship auto-extension ---


def _setup_two_agent_world(tmp_path):
    """Create a two-agent world: 'a' (张伟) and 'b' (李明)."""
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent(agents_dir, "a", "张伟")
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    # Wipe a's relationships file (default to empty so we can test
    # auto-insertion from a clean slate)
    empty_rels = RelationshipFile()
    atomic_write_json(agents_dir / "a" / "relationships.json", empty_rels.model_dump())
    return world, profiles


def _make_event_manager() -> EventQueueManager:
    return EventQueueManager(EventQueue(), random.Random(0))


def test_relationship_auto_insert_for_unknown_target(tmp_path):
    """When LLM names an in-profiles agent that's not yet in this agent's
    relationships file, the entry should be auto-inserted (not dropped)."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    # Provide tick_records with direct speech a→b so double-gate allows ±3
    tick_records = [_make_speech_tick(0, "a", "你好李明")]
    tick_records[0]["resolved_speech"] = (
        "a",
        PerceptionOutput(
            observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
            action_type=ActionType.SPEAK, action_content="你好李明",
            action_target="李明", urgency=5,
        ),
    )

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=3, trust=2, understanding=1,
                direct_interaction=True,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world,
        scene=scene,
        group_agent_ids=["a", "b"],
        day=1,
        group_id=0,
        profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=tick_records,
    )

    rels_a = world.get_agent("a").load_relationships()
    assert "b" in rels_a.relationships
    assert rels_a.relationships["b"].target_name == "李明"
    assert rels_a.relationships["b"].label == "同学"
    # Auto-inserted at zero, then delta applied (direct_interaction + tick evidence → ±3)
    assert rels_a.relationships["b"].favorability == 3
    assert rels_a.relationships["b"].trust == 2
    assert rels_a.relationships["b"].understanding == 1


def test_relationship_change_dropped_for_hallucinated_name(tmp_path):
    """LLM-fabricated target name (not in profiles) should be dropped, not crash."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="幽灵同学", favorability=5, trust=5, understanding=5),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world,
        scene=scene,
        group_agent_ids=["a", "b"],
        day=1,
        group_id=0,
        profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    # No entry created for the hallucinated name
    assert "幽灵同学" not in rels_a.relationships
    assert len(rels_a.relationships) == 0


def test_relationship_change_applied_to_existing_target(tmp_path):
    """Regression: when target already exists, the delta is applied to the
    snapshotted baseline (idempotent). Without tick evidence, double-gate
    clamps deltas to ±1."""
    world, profiles = _setup_two_agent_world(tmp_path)
    # Pre-seed a's relationship with b at favorability=10
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=10, trust=5, understanding=20,
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())

    scene = _make_scene(agent_ids=["a", "b"])
    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=2, trust=-1, understanding=3),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world,
        scene=scene,
        group_agent_ids=["a", "b"],
        day=1,
        group_id=0,
        profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    # No tick_records + no direct_interaction → clamped to ±1
    assert rels_a.relationships["b"].favorability == 11  # 10 + 1 (clamped from 2)
    assert rels_a.relationships["b"].trust == 4         # 5 - 1
    assert rels_a.relationships["b"].understanding == 21  # 20 + 1 (clamped from 3)


# --- relationship label respects source role ---


def _setup_teacher_student_world(tmp_path):
    """Create a two-agent world: teacher 't' (何老师) and student 's' (林昭宇)."""
    world, agents_dir = _setup_world(tmp_path)
    profile_t = _setup_agent(agents_dir, "t", "何老师", role=Role.HOMEROOM_TEACHER)
    profile_s = _setup_agent(agents_dir, "s", "林昭宇", role=Role.STUDENT)
    profiles = {"t": profile_t, "s": profile_s}
    # Wipe both sides' relationships so auto-insert fires from a clean slate.
    empty_rels = RelationshipFile()
    atomic_write_json(agents_dir / "t" / "relationships.json", empty_rels.model_dump())
    atomic_write_json(agents_dir / "s" / "relationships.json", empty_rels.model_dump())
    return world, profiles


def test_relationship_auto_insert_label_teacher_to_student(tmp_path):
    """When a HOMEROOM_TEACHER agent auto-inserts a student into their
    relationships, the label must be '学生' — not '同学'. Prior bug: label was
    only picked from the TARGET's role, which meant teacher→student fell
    through to '同学' and produced obviously wrong labels in state dumps."""
    world, profiles = _setup_teacher_student_world(tmp_path)
    scene = _make_scene(agent_ids=["t", "s"], name="早读")

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="林昭宇", favorability=2, trust=1, understanding=3),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"t": refl},
        world=world, scene=scene,
        group_agent_ids=["t", "s"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_t = world.get_agent("t").load_relationships()
    assert "s" in rels_t.relationships
    assert rels_t.relationships["s"].label == "学生"
    assert rels_t.relationships["s"].target_name == "林昭宇"


def test_relationship_auto_insert_label_student_to_teacher(tmp_path):
    """When a STUDENT agent auto-inserts a teacher into their relationships,
    the label must be '老师'."""
    world, profiles = _setup_teacher_student_world(tmp_path)
    scene = _make_scene(agent_ids=["t", "s"], name="早读")

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        relationship_changes=[
            AgentRelChange(to_agent="何老师", favorability=3, trust=2, understanding=1),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"s": refl},
        world=world, scene=scene,
        group_agent_ids=["t", "s"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_s = world.get_agent("s").load_relationships()
    assert "t" in rels_s.relationships
    assert rels_s.relationships["t"].label == "老师"


def test_relationship_auto_insert_label_student_to_student_is_tongxue(tmp_path):
    """Regression: student→student auto-insert must still land on '同学'."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=1, trust=1, understanding=1),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].label == "同学"


# --- recent_interactions population ---


def test_recent_interactions_recorded_on_any_nonzero_change(tmp_path):
    """Every relationship_change with non-zero deltas must append an
    interaction tag so later consumers can see 'we interacted'."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"], name="午饭", day=2)

    refl = AgentReflection(
        emotion=Emotion.HAPPY,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=3, trust=0, understanding=0),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=2, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    # Positive favorability delta → '+' valence prefix on the scene name.
    assert rels_a.relationships["b"].recent_interactions == ["Day 2 +午饭"]


def test_recent_interactions_not_recorded_for_zero_change(tmp_path):
    """A relationship_change with all deltas == 0 must NOT add a tag —
    the LLM produced a no-op and there's no interaction to record."""
    world, profiles = _setup_two_agent_world(tmp_path)
    # Pre-seed existing relationship so the edit path runs.
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=5, trust=5, understanding=5,
            recent_interactions=[],
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())
    scene = _make_scene(agent_ids=["a", "b"], name="早读")

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=0, trust=0, understanding=0),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].recent_interactions == []


def test_recent_interactions_dedup_within_same_scene(tmp_path):
    """Multiple relationship_change records in the SAME (day, scene) pair
    should collapse to a single tag — no spam from multi-tick reflections."""
    world, profiles = _setup_two_agent_world(tmp_path)
    # Pre-seed so we can feed two changes against the same target.
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=0, trust=0, understanding=0,
            recent_interactions=[],
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())
    scene = _make_scene(agent_ids=["a", "b"], name="课间", day=1)

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=1, trust=0, understanding=0),
            AgentRelChange(to_agent="李明", favorability=1, trust=0, understanding=0),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    # Two positive-delta rows against the same target in the same scene
    # dedup to a single "+课间" tag — they share a valence so the full tag
    # string is identical.
    assert rels_a.relationships["b"].recent_interactions == ["Day 1 +课间"]


def test_recent_interactions_capped_at_setting(tmp_path):
    """The per-relationship interaction log must be capped at
    settings.max_recent_interactions (default 10), keeping the most
    recent entries."""
    from sim.config import settings

    world, profiles = _setup_two_agent_world(tmp_path)
    # Pre-seed with a full 10-entry log at the current cap.
    seeded = [f"Day {d} 预存" for d in range(1, 11)]
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=0, trust=0, understanding=0,
            recent_interactions=list(seeded),
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())
    scene = _make_scene(agent_ids=["a", "b"], name="午饭", day=11)

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=1, trust=0, understanding=0),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=11, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    log = rels_a.relationships["b"].recent_interactions
    assert len(log) == settings.max_recent_interactions
    # Oldest seeded entry (Day 1) should have been evicted to make room
    # for the new Day 11 entry. The new entry carries a '+' valence prefix
    # since favorability delta was positive.
    assert "Day 1 预存" not in log
    assert "Day 11 +午饭" == log[-1]


def test_recent_interactions_negative_valence_marker(tmp_path):
    """A net-negative favorability+trust delta must produce a '−' valence
    prefix so downstream prompts can distinguish friction interactions
    from warm ones at a glance, without having to re-derive affect from
    the current absolute scores."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"], name="宿舍夜聊", day=4)

    refl = AgentReflection(
        emotion=Emotion.ANGRY,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=-4, trust=-2, understanding=1,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=4, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].recent_interactions == ["Day 4 −宿舍夜聊"]


def test_recent_interactions_neutral_valence_marker(tmp_path):
    """A non-empty change whose favorability+trust sum is zero (e.g. pure
    understanding bump, or offsetting fav/trust) must use the neutral '·'
    marker — still records the interaction happened, but without claiming
    a direction."""
    world, profiles = _setup_two_agent_world(tmp_path)
    # Pre-seed so the edit path runs.
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=0, trust=0, understanding=0,
            recent_interactions=[],
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())
    scene = _make_scene(agent_ids=["a", "b"], name="上课", day=5)

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            # understanding-only change: fav+trust = 0, but the row still
            # represents a real interaction that should be logged.
            AgentRelChange(
                to_agent="李明", favorability=0, trust=0, understanding=3,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=5, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].recent_interactions == ["Day 5 ·上课"]


def test_recent_interactions_mixed_valence_not_deduped(tmp_path):
    """Two relationship_change rows against the same target in the same
    scene with OPPOSITE valences must NOT collapse — they represent
    genuinely different moments within the scene (e.g. "disagreed, then
    reconciled") and both tags belong in the timeline."""
    world, profiles = _setup_two_agent_world(tmp_path)
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=0, trust=0, understanding=0,
            recent_interactions=[],
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())
    scene = _make_scene(agent_ids=["a", "b"], name="课间", day=3)

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        relationship_changes=[
            AgentRelChange(to_agent="李明", favorability=-2, trust=0, understanding=0),
            AgentRelChange(to_agent="李明", favorability=3, trust=1, understanding=0),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=3, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    log = rels_a.relationships["b"].recent_interactions
    assert "Day 3 −课间" in log
    assert "Day 3 +课间" in log


# --- importance write threshold ---


def test_importance_below_threshold_dropped(tmp_path):
    """A memory with importance < settings.key_memory_write_threshold (=3)
    must not land in key_memories.json."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        memories=[
            AgentMemoryCandidate(
                text="低强度记忆",
                importance=2,  # below threshold
                people=["李明"],
                location="教室",
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    km = world.get_agent("a").load_key_memories()
    assert all(m.text != "低强度记忆" for m in km.memories)


def test_importance_at_threshold_persists(tmp_path):
    """A memory at importance == threshold (=3) lands in key_memories."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        memories=[
            AgentMemoryCandidate(
                text="刚好达标的记忆",
                importance=3,  # at threshold
                people=["李明"],
                location="教室",
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    km = world.get_agent("a").load_key_memories()
    assert any(m.text == "刚好达标的记忆" for m in km.memories)


def test_importance_above_threshold_persists(tmp_path):
    """A high-importance memory passes the threshold gate."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.NEUTRAL,
        memories=[
            AgentMemoryCandidate(
                text="重要记忆",
                importance=8,
                people=["李明"],
                location="教室",
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    km = world.get_agent("a").load_key_memories()
    assert any(m.text == "重要记忆" for m in km.memories)


# --- cite_ticks 3-layer validation for new_events ---


def _make_speech_perception(content: str) -> PerceptionOutput:
    return PerceptionOutput(
        observation="x",
        inner_thought="x",
        emotion=Emotion.NEUTRAL,
        action_type=ActionType.SPEAK,
        action_content=content,
        action_target=None,
        urgency=5,
        is_disruptive=False,
    )


def _make_speech_tick(tick_idx: int, agent_id: str, content: str) -> dict:
    out = _make_speech_perception(content)
    return {
        "tick": tick_idx,
        "agent_outputs": {agent_id: out},
        "resolved_speech": (agent_id, out),
        "resolved_actions": [],
        "environmental_event": None,
        "exits": [],
    }


def test_legit_event_passes_validation(tmp_path):
    """An event whose text overlaps strongly with its cited tick passes,
    and cite_ticks + group_index are persisted on the Event."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])
    tick_records = [
        _make_speech_tick(0, "a", "我昨晚和朋友去打篮球了"),
        _make_speech_tick(1, "b", "我也喜欢篮球"),
    ]

    narrative = NarrativeExtraction(
        new_events=[
            NewEventCandidate(
                text="昨晚和朋友去打篮球",
                category="八卦",
                witnesses=["张伟", "李明"],
                cite_ticks=[1],  # 1-indexed → tick_records[0]
                spread_probability=0.5,
            ),
        ],
    )

    em = _make_event_manager()
    apply_scene_end_results(
        narrative=narrative,
        reflections={},
        world=world,
        scene=scene,
        group_agent_ids=["a", "b"],
        day=1,
        group_id=2,  # non-zero to make group_index propagation observable
        profiles=profiles,
        event_manager=em,
        tick_records=tick_records,
    )
    assert len(em.eq.events) == 1
    persisted = em.eq.events[0]
    assert persisted.cite_ticks == [1]
    assert persisted.group_index == 2


def test_missing_cite_ticks_drops_event(tmp_path):
    """Layer 1: an event with no cite_ticks must be dropped."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])
    tick_records = [_make_speech_tick(0, "a", "随便聊一句")]

    narrative = NarrativeExtraction(
        new_events=[
            NewEventCandidate(
                text="某个未注明 source 的 event",
                cite_ticks=[],  # empty
            ),
        ],
    )
    em = _make_event_manager()
    apply_scene_end_results(
        narrative=narrative, reflections={}, world=world, scene=scene,
        group_agent_ids=["a", "b"], day=1, group_id=0, profiles=profiles,
        event_manager=em, tick_records=tick_records,
    )
    assert len(em.eq.events) == 0


def test_invalid_cite_ticks_drops_event(tmp_path):
    """Layer 2: cite into a tick number that doesn't exist (e.g. 0 in
    1-indexed space, or 99) must be dropped."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])
    tick_records = [_make_speech_tick(0, "a", "随便聊一句")]

    narrative = NarrativeExtraction(
        new_events=[
            NewEventCandidate(text="event A", cite_ticks=[0]),  # 0 not valid
            NewEventCandidate(text="event B", cite_ticks=[99]),  # out of range
        ],
    )
    em = _make_event_manager()
    apply_scene_end_results(
        narrative=narrative, reflections={}, world=world, scene=scene,
        group_agent_ids=["a", "b"], day=1, group_id=0, profiles=profiles,
        event_manager=em, tick_records=tick_records,
    )
    assert len(em.eq.events) == 0


def test_cite_tick_1_indexed_matches_tick_record_0(tmp_path):
    """Regression: LLM emits cite_ticks=[1] and that must map to
    tick_records[0] (the 0-indexed first tick), because narrative.py
    displays `[Tick {tick + 1}]`."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])
    tick_records = [_make_speech_tick(0, "a", "听说今天食堂出新菜了")]

    narrative = NarrativeExtraction(
        new_events=[
            NewEventCandidate(
                text="食堂出新菜",
                cite_ticks=[1],  # 1-indexed → maps to tick 0 raw content
            ),
        ],
    )
    em = _make_event_manager()
    apply_scene_end_results(
        narrative=narrative, reflections={}, world=world, scene=scene,
        group_agent_ids=["a", "b"], day=1, group_id=0, profiles=profiles,
        event_manager=em, tick_records=tick_records,
    )
    assert len(em.eq.events) == 1


def test_cite_ticks_valid_when_scene_short_enough(tmp_path):
    """At exactly 12 ticks (the threshold) summarization does NOT trigger,
    so all tick numbers are valid."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])
    tick_records = [
        _make_speech_tick(i, "a" if i % 2 == 0 else "b", f"今天数学课讲了三角函数{i}")
        for i in range(12)
    ]

    narrative = NarrativeExtraction(
        new_events=[
            NewEventCandidate(
                text="数学课讲了三角函数",
                cite_ticks=[3],  # 1-indexed → tick 2
            ),
        ],
    )
    em = _make_event_manager()
    apply_scene_end_results(
        narrative=narrative, reflections={}, world=world, scene=scene,
        group_agent_ids=["a", "b"], day=1, group_id=0, profiles=profiles,
        event_manager=em, tick_records=tick_records,
    )
    assert len(em.eq.events) == 1


# --- Fix 5: double-gate bystander/direct relationship clamp ---


from sim.interaction.apply_results import _build_direct_interaction_set


def test_bystander_relationship_change_clamped_to_one(tmp_path):
    """LLM outputs direct_interaction=False, favorability=5 → clamped to 1."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=5, trust=3, understanding=2,
                direct_interaction=False,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].favorability == 1
    assert rels_a.relationships["b"].trust == 1
    assert rels_a.relationships["b"].understanding == 1


def test_direct_interaction_with_tick_evidence_allows_three(tmp_path):
    """direct_interaction=True + tick_records evidence (a spoke to b) → ±3 allowed."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    tick_records = [{
        "tick": 0,
        "agent_outputs": {},
        "resolved_speech": (
            "a",
            PerceptionOutput(
                observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
                action_type=ActionType.SPEAK, action_content="你好",
                action_target="李明", urgency=5,
            ),
        ),
        "resolved_actions": [],
        "environmental_event": None,
        "exits": [],
    }]

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=3, trust=-2, understanding=3,
                direct_interaction=True,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=tick_records,
    )

    rels_a = world.get_agent("a").load_relationships()
    assert rels_a.relationships["b"].favorability == 3
    assert rels_a.relationships["b"].trust == -2
    assert rels_a.relationships["b"].understanding == 3


def test_direct_interaction_without_tick_evidence_clamped_to_one(tmp_path):
    """LLM self-labels direct_interaction=True but tick_records show no a→b
    interaction → still clamped to ±1 (double-gate key test)."""
    world, profiles = _setup_two_agent_world(tmp_path)
    scene = _make_scene(agent_ids=["a", "b"])

    # tick_records exist but a never targets b
    tick_records = [{
        "tick": 0,
        "agent_outputs": {},
        "resolved_speech": (
            "a",
            PerceptionOutput(
                observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
                action_type=ActionType.SPEAK, action_content="自言自语",
                action_target=None, urgency=5,
            ),
        ),
        "resolved_actions": [],
        "environmental_event": None,
        "exits": [],
    }]

    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=3, trust=3, understanding=3,
                direct_interaction=True,  # LLM lies
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=tick_records,
    )

    rels_a = world.get_agent("a").load_relationships()
    # Double-gate: LLM said True but tick evidence says no → clamped to ±1
    assert rels_a.relationships["b"].favorability == 1
    assert rels_a.relationships["b"].trust == 1
    assert rels_a.relationships["b"].understanding == 1


def test_build_direct_interaction_set_speech_with_target():
    """Speech with action_target populates the direct set."""
    profiles = {
        "a": AgentProfile(
            agent_id="a", name="张伟", gender=Gender.MALE, role=Role.STUDENT,
            academics=Academics(overall_rank=OverallRank.MIDDLE),
            family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        ),
        "b": AgentProfile(
            agent_id="b", name="李明", gender=Gender.MALE, role=Role.STUDENT,
            academics=Academics(overall_rank=OverallRank.MIDDLE),
            family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        ),
    }
    tick_records = [{
        "tick": 0,
        "resolved_speech": (
            "a",
            PerceptionOutput(
                observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
                action_type=ActionType.SPEAK, action_content="你好",
                action_target="李明", urgency=5,
            ),
        ),
        "resolved_actions": [],
    }]

    result = _build_direct_interaction_set("a", tick_records, profiles)
    assert "b" in result


def test_build_direct_interaction_set_action_target_bidirectional():
    """Non-verbal action targeting agent is bidirectional."""
    profiles = {
        "a": AgentProfile(
            agent_id="a", name="张伟", gender=Gender.MALE, role=Role.STUDENT,
            academics=Academics(overall_rank=OverallRank.MIDDLE),
            family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        ),
        "b": AgentProfile(
            agent_id="b", name="李明", gender=Gender.MALE, role=Role.STUDENT,
            academics=Academics(overall_rank=OverallRank.MIDDLE),
            family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
        ),
    }
    # b's action targets a (张伟)
    tick_records = [{
        "tick": 0,
        "resolved_speech": None,
        "resolved_actions": [(
            "b",
            PerceptionOutput(
                observation="x", inner_thought="x", emotion=Emotion.NEUTRAL,
                action_type=ActionType.NON_VERBAL, action_content="拍肩膀",
                action_target="张伟", urgency=5,
            ),
        )],
    }]

    # From a's perspective: b targeted me → b is in my direct set
    result_a = _build_direct_interaction_set("a", tick_records, profiles)
    assert "b" in result_a

    # From b's perspective: I targeted 张伟 → a is in my direct set
    result_b = _build_direct_interaction_set("b", tick_records, profiles)
    assert "a" in result_b


def test_clamp_applies_to_baseline_path(tmp_path):
    """Pre-existing relationship + bystander change: clamp applies on top of baseline."""
    world, profiles = _setup_two_agent_world(tmp_path)
    rels = RelationshipFile(relationships={
        "b": Relationship(
            target_name="李明", target_id="b",
            favorability=50, trust=30, understanding=40,
        ),
    })
    atomic_write_json(world.agents_dir / "a" / "relationships.json", rels.model_dump())

    scene = _make_scene(agent_ids=["a", "b"])
    refl = AgentReflection(
        emotion=Emotion.CALM,
        relationship_changes=[
            AgentRelChange(
                to_agent="李明", favorability=5, trust=-5, understanding=5,
                direct_interaction=False,
            ),
        ],
    )

    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=scene,
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )

    rels_a = world.get_agent("a").load_relationships()
    # Bystander → clamped to ±1, applied to baseline
    assert rels_a.relationships["b"].favorability == 51   # 50 + 1
    assert rels_a.relationships["b"].trust == 29          # 30 - 1
    assert rels_a.relationships["b"].understanding == 41  # 40 + 1


# --- concern_lookup (PR1) ---


def _state_with_concerns(*concerns: ActiveConcern) -> AgentState:
    s = AgentState()
    for c in concerns:
        s.active_concerns.append(c)
    return s


def test_concern_lookup_by_id_exact():
    c = ActiveConcern(text="被嘲笑", id="a7f9b2")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "a7f9b2") is c


def test_concern_lookup_by_id_history():
    c = ActiveConcern(text="合并后的牵挂", id="new000", id_history=["old123"])
    state = _state_with_concerns(c)
    assert concern_lookup(state, "old123") is c


def test_concern_lookup_substring_fallback():
    """Legacy callers passing substrings still resolve."""
    c = ActiveConcern(text="被江浩天当众嘲笑数学成绩", id="a7f9b2")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "当众嘲笑") is c


def test_concern_lookup_substring_does_not_hit_when_id_wins():
    """Id match is checked before substring — id should win."""
    a = ActiveConcern(text="数学焦虑", id="aaaaaa")
    b = ActiveConcern(text="包含数学的别的牵挂", id="bbbbbb")
    state = _state_with_concerns(a, b)
    assert concern_lookup(state, "aaaaaa") is a


def test_concern_lookup_miss_returns_none():
    c = ActiveConcern(text="x", id="a1b2c3")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "zzzzzz") is None


def test_concern_lookup_empty_returns_none():
    c = ActiveConcern(text="x", id="a1b2c3")
    state = _state_with_concerns(c)
    assert concern_lookup(state, None) is None
    assert concern_lookup(state, "") is None


def test_concern_lookup_normalizes_bracketed_ref():
    """LLM-style `[ref: a7f9b2]` should resolve via id match."""
    c = ActiveConcern(text="x", id="a7f9b2")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "[ref: a7f9b2]") is c


def test_concern_lookup_normalizes_ref_prefix():
    """`ref: a7f9b2` (no brackets) also resolves."""
    c = ActiveConcern(text="x", id="a7f9b2")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "ref: a7f9b2") is c


def test_concern_lookup_case_insensitive_id():
    c = ActiveConcern(text="x", id="a7f9b2")
    state = _state_with_concerns(c)
    assert concern_lookup(state, "A7F9B2") is c


def test_concern_lookup_logs_hit_path(caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    c = ActiveConcern(text="x", id="a7f9b2")
    state = _state_with_concerns(c)
    concern_lookup(state, "a7f9b2")
    concern_lookup(state, "zzzzzz")
    # loguru routes through stderr by default; the important thing is that
    # the function does not raise and returns the correct objects. The
    # telemetry stream is verified by the other hit_path-specific tests
    # (via the return value) — this smoke test guards against regressions
    # in the logging call itself.


# --- name_aliases (PR1) ---


def test_name_alias_normalize_known():
    from sim.agent.name_aliases import normalize
    assert normalize("爸爸") == "父亲"
    assert normalize("老妈") == "母亲"


def test_name_alias_normalize_unknown_passthrough():
    from sim.agent.name_aliases import normalize
    assert normalize("江浩天") == "江浩天"


def test_name_alias_normalize_empty():
    from sim.agent.name_aliases import normalize
    assert normalize("") == ""


# --- PR2: call-site migrations ---


def _setup_agent_with_plan_and_concern(
    agents_dir,
    aid: str,
    *,
    intent_goal: str = "找陆思远聊数学",
    intent_target: str = "陆思远",
    satisfies_concern: str | None = None,
    concern_text: str = "数学焦虑",
    concern_id: str = "dead01",
    concern_intensity: int = 7,
) -> AgentProfile:
    from sim.models.agent import DailyPlan, Intention
    profile = AgentProfile(
        agent_id=aid, name="张伟", gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )
    agent_dir = agents_dir / aid
    agent_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(agent_dir / "profile.json", profile.model_dump())
    state = AgentState(
        daily_plan=DailyPlan(intentions=[
            Intention(
                target=intent_target, goal=intent_goal, reason="r",
                satisfies_concern=satisfies_concern,
            ),
        ]),
        active_concerns=[
            ActiveConcern(
                text=concern_text, id=concern_id,
                intensity=concern_intensity,
            ),
        ],
    )
    atomic_write_json(agent_dir / "state.json", state.model_dump())
    atomic_write_json(
        agent_dir / "relationships.json",
        RelationshipFile().model_dump(),
    )
    return profile


def test_fulfilled_outcome_decays_concern_by_id(tmp_path):
    """PR2: intention_outcomes → fulfilled → concern_lookup(id) → -2 intensity."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a", satisfies_concern="dead01", concern_intensity=7,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="fulfilled"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out_state = world.get_agent("a").load_state()
    assert out_state.active_concerns[0].id == "dead01"
    assert out_state.active_concerns[0].intensity == 5  # 7 - 2


def test_frustrated_outcome_bumps_concern_by_id(tmp_path):
    """PR2: intention_outcomes → frustrated → concern_lookup(id) → +1 intensity."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a", satisfies_concern="dead01", concern_intensity=5,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.FRUSTRATED,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="frustrated"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out_state = world.get_agent("a").load_state()
    assert out_state.active_concerns[0].intensity == 6  # 5 + 1


def test_satisfies_concern_fallback_substring_still_works(tmp_path):
    """Legacy intentions that reference a concern by text substring (not id)
    still resolve — the fallback path in concern_lookup covers them."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a",
        satisfies_concern="数学焦虑", concern_text="数学焦虑害怕被甩开",
        concern_id="beef99", concern_intensity=7,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="fulfilled"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out_state = world.get_agent("a").load_state()
    assert out_state.active_concerns[0].intensity == 5  # 7 - 2


def test_match_old_intention_by_shared_concern_id():
    """PR2: yesterday and today both reference the same concern id, even
    when goal text shifts ('想找爸爸聊数学' → '没敢提化学成绩')."""
    from sim.agent.daily_plan import _match_old_intention
    from sim.models.agent import Intention

    state = AgentState(
        active_concerns=[ActiveConcern(text="学业焦虑", id="beef22")],
    )
    old = Intention(
        target="父亲", goal="想找爸爸聊数学", reason="r",
        satisfies_concern="beef22", origin_day=2, pursued_days=3,
    )
    new_paraphrased = Intention(
        target="父亲", goal="没敢提化学成绩", reason="r",
        satisfies_concern="beef22",
    )
    matched = _match_old_intention(new_paraphrased, [old], state)
    assert matched is old


def test_match_old_intention_ignores_unrelated_by_different_concern():
    """Different concern ids → don't match, even with totally unrelated goals
    (no substring overlap on goals either)."""
    from sim.agent.daily_plan import _match_old_intention
    from sim.models.agent import Intention

    state = AgentState(
        active_concerns=[
            ActiveConcern(text="A", id="aaaaaa"),
            ActiveConcern(text="B", id="bbbbbb"),
        ],
    )
    old = Intention(
        target="父亲", goal="聊A", reason="r",
        satisfies_concern="aaaaaa", origin_day=1, pursued_days=1,
    )
    new = Intention(
        target="父亲", goal="完全不同的话题", reason="r",
        satisfies_concern="bbbbbb",
    )
    matched = _match_old_intention(new, [old], state)
    assert matched is None


# --- PR3: add_concern source + TTL fields + alias merge ---


def test_new_concern_reflection_source_sets_last_new_info_day():
    """PR3: a brand-new concern via source='reflection' (default) should
    have last_new_info_day seeded to `today` so it doesn't look stale on
    day 0."""
    state = AgentState()
    c = ActiveConcern(text="新焦虑", intensity=5)
    add_concern(state, c, today=3, source="reflection")
    assert state.active_concerns[0].last_new_info_day == 3
    assert state.active_concerns[0].last_reinforced_day == 3


def test_new_concern_shock_source_sets_last_new_info_day():
    """PR3: exam shock (source='shock') also seeds last_new_info_day."""
    state = AgentState()
    c = ActiveConcern(text="月考退步", intensity=8)
    add_concern(state, c, today=5, source="shock", skip_cap=True)
    assert state.active_concerns[0].last_new_info_day == 5


def test_nightly_compress_new_concern_uses_reflection_source():
    """Regression for a plan misclassification: nightly_compress produces
    `result.new_concerns` but that's reflection-style discovery, not
    consolidation. The caller must pass source='reflection' so the new
    concern survives its first end-of-day decay."""
    # Exercised indirectly: a source-reflection call on day=3 should make
    # the concern survive day=3 decay_concerns, not get evicted.
    from sim.agent.state_update import decay_concerns
    state = AgentState()
    c = ActiveConcern(text="nightly-discovered", intensity=5)
    add_concern(state, c, today=3, source="reflection")
    decay_concerns(state, today=3)
    assert len(state.active_concerns) == 1


def test_merge_reflection_advances_last_new_info_day():
    """When reflection re-surfaces an existing concern, merge updates
    last_new_info_day to today — the LLM re-emitted it, so there IS fresh info."""
    state = AgentState()
    existing = ActiveConcern(
        text="数学焦虑", topic="学业焦虑",
        related_people=["自己"], intensity=5,
        last_new_info_day=1, last_reinforced_day=1,
        reinforcement_count=0,
    )
    state.active_concerns.append(existing)
    incoming = ActiveConcern(
        text="数学焦虑（模拟考又不及格）", topic="学业焦虑",
        related_people=["自己"], intensity=6,
    )
    add_concern(state, incoming, today=4, source="reflection")
    assert existing.last_new_info_day == 4
    assert existing.last_reinforced_day == 4
    assert existing.reinforcement_count == 1


def test_concern_updates_positive_increments_count_but_not_last_new_info(tmp_path):
    """PR3: concern_updates with adjustment > 0 bumps reinforcement_count
    and last_reinforced_day, but does NOT touch last_new_info_day.
    Rationale: 'LLM says this got worse' is emotion delta, not new info."""
    from sim.interaction.apply_results import apply_scene_end_results
    from sim.models.dialogue import AgentConcernUpdate

    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a",
        concern_text="数学焦虑", concern_id="dead01",
        concern_intensity=5,
    )
    # Pre-seed day-1 fields so we can assert no-touch
    s0 = world.get_agent("a").load_state()
    s0.active_concerns[0].last_new_info_day = 1
    s0.active_concerns[0].last_reinforced_day = 1
    s0.active_concerns[0].reinforcement_count = 0
    world.get_agent("a").save_state(s0)

    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.FRUSTRATED,
        concern_updates=[
            AgentConcernUpdate(concern_text="dead01", adjustment=2),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=4, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 7
    assert out.last_reinforced_day == 4
    assert out.reinforcement_count == 1
    # KEY assertion: last_new_info_day untouched
    assert out.last_new_info_day == 1


def test_concern_updates_negative_does_not_increment_count(tmp_path):
    """PR3: concern_updates with adjustment <= 0 is pure emotion relief;
    no counters are touched."""
    from sim.interaction.apply_results import apply_scene_end_results
    from sim.models.dialogue import AgentConcernUpdate

    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a",
        concern_text="x", concern_id="dead01", concern_intensity=5,
    )
    s0 = world.get_agent("a").load_state()
    s0.active_concerns[0].last_new_info_day = 1
    s0.active_concerns[0].last_reinforced_day = 1
    s0.active_concerns[0].reinforcement_count = 0
    world.get_agent("a").save_state(s0)

    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        concern_updates=[
            AgentConcernUpdate(concern_text="dead01", adjustment=-2),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=4, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 3      # 5 - 2
    assert out.last_reinforced_day == 1   # untouched
    assert out.reinforcement_count == 0   # untouched
    assert out.last_new_info_day == 1     # untouched


def test_fulfilled_intent_bonus_minus_three_on_count(tmp_path):
    """PR3: fulfilled intention reduces reinforcement_count by 3 (reward).
    Mitigates unintentional backstop triggers after sustained frustration."""
    from sim.interaction.apply_results import apply_scene_end_results
    from sim.models.dialogue import IntentionOutcome

    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a",
        satisfies_concern="dead01", concern_intensity=7,
    )
    # Pre-seed count
    s0 = world.get_agent("a").load_state()
    s0.active_concerns[0].reinforcement_count = 8
    world.get_agent("a").save_state(s0)

    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="fulfilled"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 5
    assert out.reinforcement_count == 5  # 8 - 3


def test_alias_normalized_people_merge():
    """PR3: `爸爸` vs `父亲` collide into the same bucket via
    name_aliases.normalize — no more split concerns for the same person."""
    state = AgentState()
    dad_a = ActiveConcern(
        text="跟爸爸闹僵", topic="家庭压力",
        related_people=["爸爸"], intensity=5,
    )
    add_concern(state, dad_a, today=1, source="reflection")
    dad_b = ActiveConcern(
        text="跟父亲还是没说清", topic="家庭压力",
        related_people=["父亲"], intensity=6,
    )
    add_concern(state, dad_b, today=2, source="reflection")
    # They merged (alias normalize). One concern with bumped count.
    assert len(state.active_concerns) == 1
    assert state.active_concerns[0].reinforcement_count == 1
    assert state.active_concerns[0].last_new_info_day == 2


# --- PR7: missed_opportunity ---


def test_intention_outcome_accepts_missed_opportunity():
    """PR7: the Literal expansion accepts the new status."""
    from sim.models.dialogue import IntentionOutcome
    out = IntentionOutcome(goal="x", status="missed_opportunity")
    assert out.status == "missed_opportunity"


def test_missed_opportunity_bumps_linked_concern(tmp_path):
    """PR7: LLM-reported missed_opportunity = +1 on linked concern."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="陆思远",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.EMBARRASSED,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="missed_opportunity"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 6  # 5 + 1


def test_synthesize_missed_opportunity_when_silent_and_target_in_group(tmp_path):
    """PR7 synthesis: LLM reported nothing, target was in same group, agent
    didn't actually interact → code synthesizes +1 on linked concern."""
    world, agents_dir = _setup_world(tmp_path)
    # Agent a has an intent targeting b (LiMing in the standard helper);
    # b is in the group but a never spoke to b.
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="李明",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(emotion=Emotion.CALM)  # no intention_outcomes
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],  # no direct interaction
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 6  # 5 + 1


def test_do_not_synthesize_when_llm_reported_with_paraphrased_goal(tmp_path):
    """Cr2 regression: even if LLM paraphrases the goal ('想找李明聊' vs
    '没敢开口'), concern_match substring still bridges it, processed_intent_ids
    records the intent, and synthesis skips. Total effect: only the LLM's
    +1 is applied (not LLM +1 + synthesis +1 = +2)."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_goal="找李明聊数学",
        intent_target="李明",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(
        emotion=Emotion.EMBARRASSED,
        intention_outcomes=[
            IntentionOutcome(goal="找李明聊数学", status="missed_opportunity"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    # +1 only, not +2 (Cr2: synthesis must not double-count)
    assert out.intensity == 6


def test_do_not_synthesize_when_target_in_different_group(tmp_path):
    """PR7: synthesis scope is `group_agent_ids`, not `scene.agent_ids`.
    When the target agent exists in the scene but in a different group
    (dorm-night style), a silent no-interaction day should NOT count as
    missed."""
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="李明",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(emotion=Emotion.CALM)
    # a and b are both in scene.agent_ids but a's GROUP is just [a].
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a"],  # single-agent group: b is not in the group
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 5   # untouched — target not in group


def test_no_synthesis_when_intent_is_fulfilled(tmp_path):
    """Sanity: synthesis must not touch intents that were already
    fulfilled in this scene."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_goal="找李明说话",
        intent_target="李明",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(
        emotion=Emotion.PROUD,
        intention_outcomes=[
            IntentionOutcome(goal="找李明说话", status="fulfilled"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    # fulfilled decays by -2 (and count by -3); no synthesis +1 piled on top
    assert out.intensity == 3


# --- P1.1: pending/attempted no-op semantics ---


def test_pending_outcome_does_not_change_concern_or_intent(tmp_path):
    """`pending` is a legitimate 'still in progress' verdict — concern
    intensity must not move and the intent must stay open."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a", satisfies_concern="dead01", concern_intensity=5,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="pending"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state()
    assert out.active_concerns[0].intensity == 5  # untouched
    assert out.daily_plan.intentions[0].fulfilled is False
    assert out.daily_plan.intentions[0].abandoned is False


def test_attempted_outcome_does_not_change_concern_or_intent(tmp_path):
    """`attempted` is also still-in-progress; identical semantics."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile = _setup_agent_with_plan_and_concern(
        agents_dir, "a", satisfies_concern="dead01", concern_intensity=5,
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="attempted"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state()
    assert out.active_concerns[0].intensity == 5
    assert out.daily_plan.intentions[0].fulfilled is False
    assert out.daily_plan.intentions[0].abandoned is False


def test_pending_prevents_silence_synthesis(tmp_path):
    """If the LLM said `pending` for an intent whose target is in the
    same group but wasn't engaged, silence synthesis must NOT fire — the
    LLM already adjudicated this intent and rejected the missed-opp
    interpretation."""
    from sim.models.dialogue import IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="李明", intent_goal="找李明聊数学",
        satisfies_concern="dead01", concern_intensity=5,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(
        emotion=Emotion.CALM,
        intention_outcomes=[
            IntentionOutcome(goal="找李明聊数学", status="pending"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],  # no direct interaction
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    # No synthesis bump: intensity stays 5 (would have been 6 without
    # processed_intent_ids guard).
    assert out.intensity == 5


# --- P1.3: frustrated has no extra +1 for long pursuit ---


def test_frustrated_no_extra_bump_for_long_pursuit(tmp_path):
    """Removing the `pursued_days >= 4` extra +1: a 5-day pursuit that
    ends in frustration should bump exactly +1, not +2."""
    from sim.agent.storage import atomic_write_json
    from sim.models.agent import DailyPlan, Intention
    from sim.models.dialogue import IntentionOutcome

    world, agents_dir = _setup_world(tmp_path)
    profile = AgentProfile(
        agent_id="a", name="张伟", gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )
    agent_dir = agents_dir / "a"
    agent_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(agent_dir / "profile.json", profile.model_dump())
    state = AgentState(
        daily_plan=DailyPlan(intentions=[
            Intention(
                target="陆思远", goal="找陆思远聊数学", reason="r",
                satisfies_concern="dead01", pursued_days=5,
            ),
        ]),
        active_concerns=[
            ActiveConcern(text="数学焦虑", id="dead01", intensity=5),
        ],
    )
    atomic_write_json(agent_dir / "state.json", state.model_dump())
    atomic_write_json(
        agent_dir / "relationships.json", RelationshipFile().model_dump(),
    )
    profiles = {"a": profile}
    refl = AgentReflection(
        emotion=Emotion.FRUSTRATED,
        intention_outcomes=[
            IntentionOutcome(goal="找陆思远聊数学", status="frustrated"),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl},
        world=world, scene=_make_scene(agent_ids=["a"]),
        group_agent_ids=["a"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 6  # 5 + 1 only (was 5 + 2 before P1.3)


# --- P1.4: bump_concern_intensity helper + per-day cap ---


def test_bump_concern_intensity_caps_at_daily_limit():
    """Three +1 bumps on the same day → only the first two land; the
    third is capped to 0."""
    c = ActiveConcern(text="t", intensity=5)
    assert bump_concern_intensity(c, day=3, delta=1) == 1
    assert bump_concern_intensity(c, day=3, delta=1) == 1
    assert bump_concern_intensity(c, day=3, delta=1) == 0
    assert c.intensity == 7
    assert c.bumps_today == 2


def test_bump_concern_intensity_resets_next_day():
    """When `day` advances, the per-day budget resets lazily."""
    c = ActiveConcern(text="t", intensity=5)
    bump_concern_intensity(c, day=1, delta=1)
    bump_concern_intensity(c, day=1, delta=1)
    assert bump_concern_intensity(c, day=1, delta=1) == 0
    # New day → budget refreshed
    assert bump_concern_intensity(c, day=2, delta=1) == 1
    assert c.intensity == 8
    assert c.bumps_today == 1
    assert c.last_bump_day == 2


def test_bump_concern_intensity_ignores_negative_delta():
    """Drains bypass the cap entirely — fulfilled -2 must always land
    even after a busy day of intensify bumps."""
    c = ActiveConcern(text="t", intensity=8, bumps_today=2, last_bump_day=1)
    assert bump_concern_intensity(c, day=1, delta=-2) == -2
    assert c.intensity == 6
    # bumps_today untouched (drain doesn't consume budget)
    assert c.bumps_today == 2


def test_bump_concern_intensity_skip_cap_bypasses_limit():
    """Shock-source merges (skip_cap=True) ignore the daily cap so a
    major external event can drive the floor up even after the
    reflection cap is spent."""
    c = ActiveConcern(text="t", intensity=5, bumps_today=2, last_bump_day=1)
    assert bump_concern_intensity(c, day=1, delta=1, skip_cap=True) == 1
    assert c.intensity == 6


def test_bump_concern_intensity_capped_at_intensity_ceiling():
    """The cap caps daily DELTA, but the intensity ceiling at 10 still
    applies and clamps a too-large bump."""
    c = ActiveConcern(text="t", intensity=9)
    # daily_cap=2 lets +2 through, but intensity ceiling at 10 clamps.
    applied = bump_concern_intensity(c, day=1, delta=2)
    assert applied == 2
    assert c.intensity == 10


def test_same_concern_hit_by_multiple_paths_single_day(tmp_path):
    """Realistic scenario: silence-synth + concern_updates +2 +
    frustrated all hit the same concern in one reflection cycle. The
    P1.4 cap means net intensity rises by 2, not 4."""
    from sim.models.dialogue import AgentConcernUpdate, IntentionOutcome
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="李明", intent_goal="找李明聊数学",
        satisfies_concern="dead01", concern_intensity=4,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(
        emotion=Emotion.FRUSTRATED,
        intention_outcomes=[
            IntentionOutcome(goal="找李明聊数学", status="frustrated"),
        ],
        concern_updates=[
            AgentConcernUpdate(concern_text="dead01", adjustment=2),
        ],
    )
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    # frustrated path lands its +1 first (uses 1 of 2). concern_updates
    # +2 then asks for 2 but only 1 remains in budget. Net: +2, not +3.
    # Silence synth never runs because frustrated already populated
    # processed_intent_ids for this intent.
    assert out.intensity == 6


# --- P2.B.2: silence synth ≥7 immune ---


def test_silence_synthesis_skips_high_intensity_concern(tmp_path):
    """When the linked concern is already at intensity ≥7, silence
    synthesis must not fire — running an already-loud concern up to 10
    via 'didn't talk to them today' adds no signal."""
    world, agents_dir = _setup_world(tmp_path)
    profile_a = _setup_agent_with_plan_and_concern(
        agents_dir, "a", intent_target="李明", intent_goal="找李明聊数学",
        satisfies_concern="dead01", concern_intensity=8,
    )
    profile_b = _setup_agent(agents_dir, "b", "李明")
    profiles = {"a": profile_a, "b": profile_b}
    refl = AgentReflection(emotion=Emotion.CALM)  # no intention_outcomes
    apply_scene_end_results(
        narrative=NarrativeExtraction(),
        reflections={"a": refl, "b": AgentReflection()},
        world=world, scene=_make_scene(agent_ids=["a", "b"]),
        group_agent_ids=["a", "b"],
        day=1, group_id=0, profiles=profiles,
        event_manager=_make_event_manager(),
        tick_records=[],
    )
    out = world.get_agent("a").load_state().active_concerns[0]
    assert out.intensity == 8  # unchanged — the ≥7 immune gate held
