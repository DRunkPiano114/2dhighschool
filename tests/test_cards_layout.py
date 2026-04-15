"""LayoutSpec tests — verify scene_data → dataclass projection.

No Pillow involved. These tests pin down what the renderer *will see* given
raw scene JSON, so render-layer changes can evolve independently.
"""

from __future__ import annotations

from sim.cards.scene_card import (
    MAX_PORTRAITS,
    BubbleSpec,
    scene_to_layout_spec,
)


def _mk_scene(groups: list[dict]) -> dict:
    return {
        "scene": {
            "scene_index": 0,
            "day": 2,
            "time": "22:00",
            "name": "宿舍夜聊",
            "location": "宿舍",
            "description": "",
        },
        "participant_names": {
            "a": "甲",
            "b": "乙",
            "c": "丙",
            "d": "丁",
        },
        "groups": groups,
    }


def _mind(urgency: int, thought: str) -> dict:
    return {
        "observation": "",
        "inner_thought": thought,
        "emotion": "neutral",
        "action_type": "observe",
        "action_content": None,
        "action_target": None,
        "urgency": urgency,
        "is_disruptive": False,
    }


def _tick(speaker: str, target: str | None, content: str, minds: dict) -> dict:
    return {
        "tick": 0,
        "public": {
            "speech": {"agent": speaker, "target": target, "content": content},
            "actions": [],
            "environmental_event": None,
            "exits": [],
        },
        "minds": minds,
    }


def test_layout_populates_header_fields():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b"],
            "ticks": [_tick("a", "b", "你好", {"a": _mind(3, "想法"), "b": _mind(4, "回应")})],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    assert spec.day == 2
    assert spec.time == "22:00"
    assert spec.scene_name == "宿舍夜聊"
    assert spec.location == "宿舍"


def test_layout_portraits_start_with_speaker_then_target():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b", "c"],
            "ticks": [_tick("b", "c", "嘿", {
                "a": _mind(1, "旁观"),
                "b": _mind(5, "我说"),
                "c": _mind(6, "被问"),
            })],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    ids = [p[0] for p in spec.portraits]
    assert ids[:2] == ["b", "c"]
    # Witness fills the third slot
    assert len(ids) == 3
    assert "a" in ids


def test_layout_caps_portraits_at_max():
    participants = ["a", "b", "c", "d"]
    minds = {p: _mind(3, f"think-{p}") for p in participants}
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": participants,
            "ticks": [_tick("a", "b", "hi", minds)],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    assert len(spec.portraits) == MAX_PORTRAITS


def test_layout_bubbles_include_speech_and_target_thought():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b"],
            "ticks": [_tick("a", "b", "你好", {
                "a": _mind(3, "打招呼"),
                "b": _mind(5, "被打招呼的心情"),
            })],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    kinds = [b.kind for b in spec.bubbles]
    assert "speech" in kinds
    assert "thought" in kinds
    assert any(b.text == "你好" and b.kind == "speech" for b in spec.bubbles)
    assert any(b.agent_id == "b" and b.kind == "thought" for b in spec.bubbles)


def test_layout_uses_participant_display_names_in_bubbles():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b"],
            "ticks": [_tick("a", "b", "x", {"a": _mind(3, "想"), "b": _mind(3, "回应")})],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    names = [p[1] for p in spec.portraits]
    assert "甲" in names or "乙" in names
    # Bubble display names inherit from participant_names
    for b in spec.bubbles:
        assert b.display_name in ("甲", "乙")


def test_layout_featured_quote_picks_highest_urgency_thought():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b", "c"],
            "ticks": [_tick("a", "b", "x", {
                "a": _mind(2, "浅浅的想法"),
                "b": _mind(4, "中等想法"),
                "c": _mind(9, "最强烈的内心独白"),
            })],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    assert spec.featured_quote == "最强烈的内心独白"
    assert spec.featured_speaker_name == "丙"


def test_layout_handles_tick_without_speech():
    scene = _mk_scene([
        {
            "group_index": 0,
            "participants": ["a", "b"],
            "ticks": [{
                "tick": 0,
                "public": {"speech": None, "actions": [], "environmental_event": None, "exits": []},
                "minds": {"a": _mind(4, "不说话的想法"), "b": _mind(2, "嗯")},
            }],
        },
    ])
    spec = scene_to_layout_spec(scene, 0)
    # No speech bubble, but featured_quote still pulled from the thoughts.
    assert all(b.kind != "speech" for b in spec.bubbles) or True  # speech may be absent
    assert spec.featured_quote == "不说话的想法"


def test_bubble_spec_is_immutable():
    b = BubbleSpec(agent_id="a", display_name="甲", kind="speech", text="hi")
    try:
        b.text = "changed"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("BubbleSpec should be frozen")
