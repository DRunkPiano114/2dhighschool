"""Daily aggregation tests — pure heuristics, no Pillow.

Covers headline selection, CP detection, mood dominance, golden-quote dedup,
and the scene_thumbs projection. These pin the behaviour the daily JSON API
endpoint returns.
"""

from __future__ import annotations

from sim.cards.aggregations import (
    compute_mood_map,
    pick_cp,
    pick_golden_quote,
    pick_headline,
    pick_secondaries,
    scene_thumbs,
    summary_to_dict,
    DailySummary,
)


# --- Fixtures --------------------------------------------------------------


def _mind(urgency: int, thought: str, emotion: str = "neutral") -> dict:
    return {
        "observation": "",
        "inner_thought": thought,
        "emotion": emotion,
        "action_type": "speak",
        "action_content": None,
        "action_target": None,
        "urgency": urgency,
        "is_disruptive": False,
    }


def _tick(speaker: str | None, content: str | None, minds: dict) -> dict:
    return {
        "tick": 0,
        "public": {
            "speech": {"agent": speaker, "target": None, "content": content} if speaker else None,
            "actions": [],
            "environmental_event": None,
            "exits": [],
        },
        "minds": minds,
    }


def _scene(time: str, name: str, location: str, file: str, groups: list[dict]) -> dict:
    return {
        "scene": {"day": 1, "time": time, "name": name, "location": location},
        "participant_names": {
            "fang_yuchen": "方语晨",
            "lin_zhaoyu": "林昭宇",
            "lu_siyuan": "陆思远",
        },
        "groups": groups,
        "_index_entry": {"file": file},
    }


# --- Tests -----------------------------------------------------------------


def test_pick_headline_prefers_rich_thought_over_urgency():
    scenes = [
        _scene(
            "07:00", "早读", "教室", "0700_早读.json",
            [
                {
                    "group_index": 0,
                    "participants": ["lin_zhaoyu", "lu_siyuan"],
                    "ticks": [_tick("lin_zhaoyu", "嘿", {
                        "lin_zhaoyu": _mind(9, "短想"),  # high urgency, short
                    })],
                    "reflections": {},
                },
                {
                    "group_index": 1,
                    "participants": ["fang_yuchen", "lu_siyuan"],
                    "ticks": [_tick("fang_yuchen", "x", {
                        "fang_yuchen": _mind(4, "一段足够长的内心独白，超过十五个字的描述"),
                    })],
                    "reflections": {},
                },
            ],
        ),
    ]
    h = pick_headline(scenes)
    assert h is not None
    assert len(h.thought or "") >= 15


def test_pick_headline_returns_none_on_empty_day():
    assert pick_headline([]) is None


def test_pick_secondaries_excludes_headline_scene():
    scenes = [
        _scene(
            "07:00", "早读", "教室", "0700_早读.json",
            [{
                "group_index": 0,
                "participants": ["a", "b"],
                "ticks": [_tick("a", "x", {"a": _mind(9, "非常长的想法用来拿头条位置")})],
                "reflections": {},
            }],
        ),
        _scene(
            "12:00", "午饭", "食堂", "1200_午饭@食堂.json",
            [{
                "group_index": 0,
                "participants": ["a", "b"],
                "ticks": [_tick("a", "y", {"a": _mind(5, "稍弱一点的想法")})],
                "reflections": {},
            }],
        ),
    ]
    headline = pick_headline(scenes)
    secondaries = pick_secondaries(scenes, headline, limit=3)
    files = [s.scene_file for s in secondaries]
    assert "0700_早读.json" not in files


def test_compute_mood_map_returns_dominant_emotion_per_agent():
    scenes = [
        _scene(
            "07:00", "x", "y", "0.json",
            [{
                "group_index": 0,
                "participants": ["fang_yuchen"],
                "ticks": [
                    _tick("fang_yuchen", "x", {"fang_yuchen": _mind(1, "a", emotion="happy")}),
                    _tick("fang_yuchen", "x", {"fang_yuchen": _mind(1, "b", emotion="happy")}),
                    _tick("fang_yuchen", "x", {"fang_yuchen": _mind(1, "c", emotion="anxious")}),
                ],
                "reflections": {},
            }],
        ),
    ]
    moods = compute_mood_map(scenes)
    assert len(moods) == 1
    assert moods[0].agent_id == "fang_yuchen"
    assert moods[0].dominant_emotion == "happy"
    assert moods[0].emotion_counts["happy"] == 2
    assert moods[0].emotion_counts["anxious"] == 1


def test_pick_cp_sums_both_directions_of_a_pair():
    scenes = [
        _scene(
            "12:00", "午饭", "食堂", "1200_午饭@食堂.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan"],
                "ticks": [],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "happy",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": 3, "trust": 2, "understanding": 1}
                        ],
                        "memories": [],
                        "new_concerns": [],
                    },
                    "lu_siyuan": {
                        "emotion": "happy",
                        "relationship_changes": [
                            {"to_agent": "林昭宇", "favorability": 2, "trust": 1, "understanding": 1}
                        ],
                        "memories": [],
                        "new_concerns": [],
                    },
                },
            }],
        ),
    ]
    cp = pick_cp(scenes)
    assert cp is not None
    assert {cp.a_id, cp.b_id} == {"lin_zhaoyu", "lu_siyuan"}
    # Sum across both directions
    assert cp.favorability_delta == 5
    assert cp.trust_delta == 3
    assert cp.understanding_delta == 2


def test_pick_cp_returns_none_when_no_positive_motion():
    scenes = [
        _scene(
            "12:00", "x", "y", "x.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan"],
                "ticks": [],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "angry",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": -2, "trust": -1, "understanding": 0}
                        ],
                        "memories": [],
                        "new_concerns": [],
                    },
                },
            }],
        ),
    ]
    assert pick_cp(scenes) is None


def test_pick_golden_quote_excludes_headline_text():
    scenes = [
        _scene(
            "07:00", "x", "y", "0.json",
            [{
                "group_index": 0,
                "participants": ["a", "b"],
                "ticks": [
                    _tick("a", "hi", {"a": _mind(9, "这是头条想法，会被排除。")}),
                    _tick("a", "hi", {"a": _mind(4, "这是金句候选，应被选中。")}),
                ],
                "reflections": {},
            }],
        ),
    ]
    quote = pick_golden_quote(scenes, exclude_text="这是头条想法，会被排除。")
    assert quote is not None
    assert quote.text != "这是头条想法，会被排除。"


def test_scene_thumbs_flattens_participants():
    scenes = [
        _scene(
            "07:00", "早读", "教室", "0700.json",
            [
                {"group_index": 0, "participants": ["a", "b"], "ticks": [], "reflections": {}},
                {"group_index": 1, "participants": ["b", "c"], "ticks": [], "reflections": {}},
            ],
        ),
    ]
    thumbs = scene_thumbs(scenes)
    assert len(thumbs) == 1
    assert thumbs[0]["participants"] == ["a", "b", "c"]


def test_summary_to_dict_is_json_friendly():
    s = DailySummary(day=1, headline=None)
    d = summary_to_dict(s)
    # No dataclasses leaking into the serialized shape.
    import json
    json.dumps(d, ensure_ascii=False)
    assert d["day"] == 1
    assert d["headline"] is None
