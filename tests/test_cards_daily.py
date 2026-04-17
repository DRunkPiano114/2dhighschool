"""Daily aggregation tests — pure heuristics, no Pillow.

Covers headline selection, CP detection, mood dominance, golden-quote dedup,
and the scene_thumbs projection. These pin the behaviour the daily JSON API
endpoint returns.
"""

from __future__ import annotations

from sim.cards.aggregations import (
    CONTRAST_FAILED_INTENT_MIN_URGENCY,
    CONTRAST_MISMATCH_MIN_FAV_DELTA,
    CONTRAST_MISMATCH_MIN_VALENCE_DELTA,
    CONTRAST_SILENT_JUDGMENT_MIN_SUM,
    DailySummary,
    _assert_valence_exhaustive,
    compute_mood_map,
    pick_concern_spotlight,
    pick_contrast,
    pick_cp,
    pick_golden_quote,
    pick_headline,
    pick_secondaries,
    pick_top_event,
    scene_thumbs,
    summary_to_dict,
)
from sim.cards.history import DailyHistory
from sim.models.agent import ActiveConcern
from sim.models.event import EventQueue


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
    # New card slots are present (null when nothing picked).
    assert "top_event" in d
    assert "contrast" in d
    assert "concern_spotlight" in d


# --- Phase A: top_event / contrast / concern_spotlight --------------------


def _new_event(
    text: str,
    category: str,
    witnesses: list[str],
    cite_ticks: list[int],
    spread_probability: float = 0.6,
) -> dict:
    return {
        "text": text,
        "category": category,
        "witnesses": witnesses,
        "spread_probability": spread_probability,
        "cite_ticks": cite_ticks,
    }


def test_valence_map_is_exhaustive_for_emotion_enum():
    # Fails loudly if someone adds an Emotion member without updating the
    # valence table — we want CI to catch the drift, not production.
    _assert_valence_exhaustive()


def test_pick_top_event_returns_none_on_empty_day():
    scenes = [
        _scene(
            "07:00", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu"],
                "ticks": [],
                "reflections": {},
                "narrative": {"new_events": []},
            }],
        ),
    ]
    assert pick_top_event(scenes) is None


def test_pick_top_event_prefers_gossip_category_over_academic():
    # Same spread + witness count — the "八卦" one should win solely on
    # category weight. This pins the intent of `_category_weight`, not its
    # specific hand-tuned numbers.
    scenes = [
        _scene(
            "08:45", "课间", "教室", "0845.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan"],
                "ticks": [
                    _tick("lin_zhaoyu", "", {
                        "lin_zhaoyu": _mind(7, "八卦想法写得足够长，至少十二个字"),
                    }),
                ],
                "reflections": {},
                "narrative": {
                    "new_events": [
                        _new_event(
                            "某某和某某牵手被看到", "八卦",
                            ["林昭宇", "陆思远"], [0],
                        ),
                        _new_event(
                            "某某某提交了物理作业", "学习进度",
                            ["林昭宇", "陆思远"], [0],
                        ),
                    ],
                },
            }],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.category == "八卦"


def test_pick_top_event_pull_quote_respects_witness_and_cite():
    # Event witnesses = lin_zhaoyu & lu_siyuan; tang_shihan's inner thought
    # shouldn't be chosen even if it's louder. pull_quote_agent_id must be
    # one of the witnesses.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan", "tang_shihan"],
                "ticks": [_tick("tang_shihan", "", {
                    "tang_shihan": _mind(9, "无关目击者的吼叫太响亮应当被忽略"),
                    "lu_siyuan": _mind(3, "目击者的心声稍淡但会被选中"),
                })],
                "reflections": {},
                "narrative": {
                    "new_events": [
                        _new_event(
                            "某事发生", "八卦",
                            ["林昭宇", "陆思远"], [0],
                        ),
                    ],
                },
            }],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.pull_quote_agent_id == "lu_siyuan"
    assert card.pull_quote and "目击者的心声" in card.pull_quote


def test_pick_top_event_pull_quote_none_when_no_witness_thought():
    # No inner_thought at cite_ticks belongs to a witness — pull_quote is
    # optional, so the card still renders with pull_quote=None.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "tang_shihan"],
                "ticks": [_tick("tang_shihan", "", {
                    "tang_shihan": _mind(5, "非目击者的很长的心声"),
                })],
                "reflections": {},
                "narrative": {
                    "new_events": [
                        _new_event(
                            "事件", "八卦",
                            ["林昭宇"], [0],
                        ),
                    ],
                },
            }],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.pull_quote is None
    assert card.pull_quote_agent_id is None


def test_pick_top_event_tick_falls_back_to_cite_tick_when_no_pull_quote():
    # No witness has a thought on any cite_tick → pull_quote resolves to None.
    # The deep-link tick must still point *into* the cited region, not snap
    # to 0, so "进入现场" lands on the event's beat instead of the scene top.
    # Uses cite_ticks=[3] with a witness (lin_zhaoyu) who is silent on that
    # tick but speaks elsewhere, plus a non-witness with thoughts.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "tang_shihan"],
                "ticks": [
                    _tick("lin_zhaoyu", "", {"lin_zhaoyu": _mind(3, "0号位的长心声")}),
                    _tick("lin_zhaoyu", "", {}),
                    _tick("lin_zhaoyu", "", {}),
                    _tick("lin_zhaoyu", "", {"tang_shihan": _mind(5, "非目击者说话了")}),
                ],
                "reflections": {},
                "narrative": {
                    "new_events": [
                        _new_event("事件", "八卦", ["林昭宇"], [3]),
                    ],
                },
            }],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.pull_quote is None
    assert card.tick_index == 3


def test_pick_top_event_tick_fallback_handles_one_indexed_cite():
    # Some LLM traces emit 1-indexed cite_ticks. A cite_tick of `len(ticks)`
    # is out of range as-is but valid when treated as 1-indexed (len-1). The
    # fallback must probe (t, t-1) the same way `_pull_quote_from_group` does.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu"],
                "ticks": [
                    _tick("lin_zhaoyu", "", {}),
                    _tick("lin_zhaoyu", "", {}),
                    _tick("lin_zhaoyu", "", {}),
                ],
                "reflections": {},
                "narrative": {
                    "new_events": [
                        # cite_ticks=[3] with only 3 ticks → 1-indexed, normalize to 2.
                        _new_event("事件", "八卦", ["林昭宇"], [3]),
                    ],
                },
            }],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.pull_quote is None
    assert card.tick_index == 2


def test_pick_top_event_works_without_group_index_on_event():
    # Scene JSON exports `new_events` without `group_index` — pick_top_event
    # must NOT rely on the field and must still locate the right group by
    # iterating.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [
                {
                    "group_index": 0,
                    "participants": ["lin_zhaoyu"],
                    "ticks": [_tick("lin_zhaoyu", "", {
                        "lin_zhaoyu": _mind(5, "第一组心声不足以定位到第二组"),
                    })],
                    "reflections": {},
                    "narrative": {"new_events": []},
                },
                {
                    "group_index": 1,
                    "participants": ["lu_siyuan"],
                    "ticks": [_tick("lu_siyuan", "", {
                        "lu_siyuan": _mind(4, "正确组的心声应当被选中配文"),
                    })],
                    "reflections": {},
                    "narrative": {
                        "new_events": [
                            # NOTE: no `group_index` field on purpose.
                            _new_event(
                                "第二组里的事件", "八卦",
                                ["陆思远"], [0],
                            ),
                        ],
                    },
                },
            ],
        ),
    ]
    card = pick_top_event(scenes, min_score=0.0)
    assert card is not None
    assert card.pull_quote_agent_id == "lu_siyuan"


def test_pick_contrast_prefers_mismatch_over_failed_intent():
    # Both a mismatch *and* a failed_intent are present — priority ordering
    # should yield mismatch; that pins the "drama density" ordering.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan"],
                "ticks": [
                    _tick("lin_zhaoyu", None, {
                        "lin_zhaoyu": _mind(8, "开心到想笑出来，真是完美一天", emotion="happy"),
                        "lu_siyuan": _mind(8, "这个人让我烦透了，气到说不出话", emotion="angry"),
                    }),
                ],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "happy",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": 3, "trust": 0, "understanding": 0, "direct_interaction": True},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [
                            {"goal": "失败目标", "status": "frustrated", "brief_reason": "很长的失败原因说明充分"},
                        ],
                    },
                    "lu_siyuan": {
                        "emotion": "angry",
                        "relationship_changes": [
                            {"to_agent": "林昭宇", "favorability": -3, "trust": 0, "understanding": 0, "direct_interaction": True},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                },
            }],
        ),
    ]
    c = pick_contrast(scenes)
    assert c is not None
    assert c.kind == "mismatch"
    assert c.payload["a_name"] in ("林昭宇", "陆思远")
    assert c.payload["b_name"] in ("林昭宇", "陆思远")


def test_pick_contrast_failed_intent_when_no_mismatch():
    # Only a failed_intent signal present — gate should pass, kind =
    # "failed_intent".
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu"],
                "ticks": [_tick("lin_zhaoyu", None, {
                    "lin_zhaoyu": _mind(CONTRAST_FAILED_INTENT_MIN_URGENCY + 1, "目标失败的心声"),
                })],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "frustrated",
                        "relationship_changes": [],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [
                            {"goal": "想跟他道歉", "status": "missed_opportunity", "brief_reason": "人多没好意思开口讲这事儿"},
                        ],
                    },
                },
            }],
        ),
    ]
    c = pick_contrast(scenes)
    assert c is not None
    assert c.kind == "failed_intent"
    assert c.payload["agent_id"] == "lin_zhaoyu"
    assert c.payload["status"] == "missed_opportunity"


def test_pick_contrast_silent_judgment_aggregates_accusers():
    # Two accusers quietly knock lu_siyuan's favorability without direct
    # interaction. Silent judgment is the only kind that passes — check the
    # accuser list carries both.
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["fang_yuchen", "lin_zhaoyu", "lu_siyuan"],
                "ticks": [],
                "reflections": {
                    "fang_yuchen": {
                        "emotion": "neutral",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": -2, "trust": 0, "understanding": 0, "direct_interaction": False},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                    "lin_zhaoyu": {
                        "emotion": "neutral",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": -2, "trust": 0, "understanding": 0, "direct_interaction": False},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                },
            }],
        ),
    ]
    c = pick_contrast(scenes)
    assert c is not None
    assert c.kind == "silent_judgment"
    assert c.payload["target_id"] == "lu_siyuan"
    accusers = {a["id"] for a in c.payload["accusers"]}
    assert accusers == {"fang_yuchen", "lin_zhaoyu"}
    assert c.score >= CONTRAST_SILENT_JUDGMENT_MIN_SUM
    # Silent judgment is cross-scene by construction — no single scene pointer.
    # The UI hides the "进入现场" link when these are None.
    assert c.scene_file is None
    assert c.scene_time is None
    assert c.scene_name is None


def test_pick_contrast_returns_none_below_all_thresholds():
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu"],
                "ticks": [_tick("lin_zhaoyu", None, {
                    "lin_zhaoyu": _mind(1, "太短了"),
                })],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "neutral",
                        "relationship_changes": [],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                },
            }],
        ),
    ]
    assert pick_contrast(scenes) is None


def test_pick_contrast_mismatch_requires_both_deltas():
    # Valence swings hard but fav_delta is 0 → mismatch rejected even though
    # it looks dramatic. Guards against the gate being too lax.
    low_fav_delta = max(0, CONTRAST_MISMATCH_MIN_FAV_DELTA - 1)
    scenes = [
        _scene(
            "08:45", "x", "y", "a.json",
            [{
                "group_index": 0,
                "participants": ["lin_zhaoyu", "lu_siyuan"],
                "ticks": [_tick("lin_zhaoyu", None, {
                    "lin_zhaoyu": _mind(5, "非常开心的长心声应当足够长", emotion="happy"),
                    "lu_siyuan": _mind(5, "非常愤怒的长心声应当足够长", emotion="angry"),
                })],
                "reflections": {
                    "lin_zhaoyu": {
                        "emotion": "happy",
                        "relationship_changes": [
                            {"to_agent": "陆思远", "favorability": low_fav_delta, "trust": 0, "understanding": 0, "direct_interaction": True},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                    "lu_siyuan": {
                        "emotion": "angry",
                        "relationship_changes": [
                            {"to_agent": "林昭宇", "favorability": low_fav_delta, "trust": 0, "understanding": 0, "direct_interaction": True},
                        ],
                        "memories": [],
                        "new_concerns": [],
                        "intention_outcomes": [],
                    },
                },
            }],
        ),
    ]
    _ = CONTRAST_MISMATCH_MIN_VALENCE_DELTA  # doc-touch
    c = pick_contrast(scenes)
    if c is not None:
        assert c.kind != "mismatch"


def test_pick_concern_spotlight_cross_day_prefers_reinforced():
    # Two concerns, one with higher reinforcement_count — it should win
    # over the purely-higher-intensity one, because accumulation is the
    # whole point of the card.
    fresh = ActiveConcern(
        id="a", text="今天刚起的心事", topic="学业焦虑",
        intensity=9, source_day=7, last_reinforced_day=7,
        reinforcement_count=0,
    )
    stuck = ActiveConcern(
        id="b", text="连载了一周的心事", topic="恋爱",
        intensity=5, source_day=1, last_reinforced_day=7,
        reinforcement_count=5,
    )
    history = DailyHistory(
        active_concerns_by_agent={"fang_yuchen": [fresh], "lin_zhaoyu": [stuck]},
        event_queue=EventQueue(),
    )
    card = pick_concern_spotlight(scenes=[], day=7, history=history)
    assert card is not None
    assert card.agent_id == "lin_zhaoyu"
    assert card.days_active == 7
    assert card.first_day == 1
    assert card.reinforcement_count == 5
    assert card.reinforced_today is True


def test_pick_concern_spotlight_single_day_when_history_none():
    scenes = [
        _scene(
            "12:00", "午饭", "食堂", "1200.json",
            [{
                "group_index": 0,
                "participants": ["fang_yuchen"],
                "ticks": [],
                "reflections": {
                    "fang_yuchen": {
                        "emotion": "anxious",
                        "relationship_changes": [],
                        "memories": [],
                        "new_concerns": [
                            {
                                "text": "担心明天的考试",
                                "intensity": 7,
                                "topic": "学业焦虑",
                                "positive": False,
                            },
                        ],
                        "intention_outcomes": [],
                    },
                },
            }],
        ),
    ]
    card = pick_concern_spotlight(scenes=scenes, day=3, history=None)
    assert card is not None
    assert card.agent_id == "fang_yuchen"
    assert card.reinforcement_count == 0
    assert card.days_active == 1
    assert card.first_day == 3
    assert card.reinforced_today is True


def test_pick_concern_spotlight_returns_none_when_nothing_today_and_no_history():
    scenes = [
        _scene(
            "12:00", "午饭", "食堂", "1200.json",
            [{
                "group_index": 0,
                "participants": ["fang_yuchen"],
                "ticks": [],
                "reflections": {},
            }],
        ),
    ]
    assert pick_concern_spotlight(scenes=scenes, day=1, history=None) is None


def test_load_history_returns_none_for_historical_days(tmp_path, monkeypatch):
    # Fake a days export with day_001..day_003. Asking for day_001/day_002
    # while latest=day_003 → None (would fabricate future data). Latest day →
    # DailyHistory object, even if no agent state persisted yet (graceful).
    from sim.cards import history as history_mod

    days_root = tmp_path / "days"
    for n in (1, 2, 3):
        (days_root / f"day_{n:03d}").mkdir(parents=True)

    monkeypatch.setattr(history_mod, "DAYS_DIR", days_root)

    agents_root = tmp_path / "state"
    agents_root.mkdir()
    monkeypatch.setattr(history_mod.settings, "agents_dir", agents_root)
    monkeypatch.setattr(history_mod.settings, "world_dir", tmp_path / "world")

    assert history_mod.load_history(up_to_day=1) is None
    assert history_mod.load_history(up_to_day=2) is None
    # Latest day → returns DailyHistory (possibly empty, still truthy).
    h = history_mod.load_history(up_to_day=3)
    assert isinstance(h, DailyHistory)
    assert h.active_concerns_by_agent == {}


def test_load_history_returns_none_when_no_days_exported(tmp_path, monkeypatch):
    from sim.cards import history as history_mod

    monkeypatch.setattr(history_mod, "DAYS_DIR", tmp_path / "nonexistent")
    assert history_mod.load_history(up_to_day=1) is None


def test_load_history_returns_none_when_agents_dir_missing(tmp_path, monkeypatch):
    # Fresh clone: days exist but no simulation/state/ — must not crash.
    from sim.cards import history as history_mod

    days_root = tmp_path / "days"
    (days_root / "day_001").mkdir(parents=True)
    monkeypatch.setattr(history_mod, "DAYS_DIR", days_root)
    monkeypatch.setattr(history_mod.settings, "agents_dir", tmp_path / "nonexistent_state")
    monkeypatch.setattr(history_mod.settings, "world_dir", tmp_path / "nonexistent_world")
    assert history_mod.load_history(up_to_day=1) is None
