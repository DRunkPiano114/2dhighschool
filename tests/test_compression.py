"""Tests for memory compression and consolidation (PR5)."""

from pathlib import Path

from sim.memory.compression import (
    ConsolidationResult,
    DAILY_HIGHLIGHT_FALLBACK_POOL,
    MergeGroup,
    SUMMARY_FALLBACK_MAX_LEN,
    _apply_consolidation,
    _cluster_concerns_by_topic_and_people,
    _validate_daily_highlight,
)
from sim.models.agent import ActiveConcern, AgentState
from sim.models.memory import KeyMemory, KeyMemoryFile


class _FakeStorage:
    """Minimal AgentStorage stand-in for _apply_consolidation tests."""
    def __init__(self):
        self.km_file = KeyMemoryFile()
        self.state = AgentState()

    @property
    def agent_id(self) -> str:
        return "test"

    def write_key_memories(self, km_file):
        self.km_file = km_file

    def save_state(self, state):
        self.state = state


def _kept(kind, cluster_id, indices, prefixes, final=5):
    return MergeGroup(
        cluster_kind=kind, cluster_id=cluster_id,
        source_indices=indices, source_text_prefixes=prefixes,
        final_intensity_or_importance=final,
    )


def test_consolidation_prefix_strict_match_works():
    """Exact 15-char prefix still works (existing behavior preserved)."""
    s = _FakeStorage()
    s.state.active_concerns = [
        ActiveConcern(text="化学竞赛一次一次失败的记忆", id="aaaaaa"),
        ActiveConcern(text="化学竞赛第二次也没考好", id="bbbbbb"),
    ]
    clusters = _cluster_concerns_by_topic_and_people(s.state.active_concerns)
    result = ConsolidationResult(merge_groups=[
        _kept("concern", 1, [1, 2], ["化学竞赛一次一次失败", "化学竞赛第二次也没考好"]),
    ])
    _apply_consolidation(
        s, s.km_file, s.state, result, today=1,
        memory_clusters=[], concern_clusters=clusters,
    )
    assert len(s.state.active_concerns) == 1


def test_consolidation_prefix_accepts_llm_full_text():
    """PR5: LLM returned the complete text (not truncated to 15 chars).
    The old strict `[:15] == [:15]` would fail; bidirectional startswith
    accepts this."""
    s = _FakeStorage()
    full_text = "化学竞赛一次一次失败的长篇记忆累积"
    s.state.active_concerns = [
        ActiveConcern(text=full_text, id="aaaaaa"),
        ActiveConcern(text="化学焦虑加重", id="bbbbbb"),
    ]
    clusters = _cluster_concerns_by_topic_and_people(s.state.active_concerns)
    result = ConsolidationResult(merge_groups=[
        # LLM echoed the full text instead of just the 15-char prefix
        _kept("concern", 1, [1, 2], [full_text, "化学焦虑加重"]),
    ])
    _apply_consolidation(
        s, s.km_file, s.state, result, today=1,
        memory_clusters=[], concern_clusters=clusters,
    )
    assert len(s.state.active_concerns) == 1


def test_consolidation_prefix_accepts_short_llm_prefix():
    """PR5: LLM returned a short prefix (< 15 chars). Bidirectional
    startswith also accepts — the short LLM prefix is a prefix of the
    actual 15-char prefix."""
    s = _FakeStorage()
    s.state.active_concerns = [
        ActiveConcern(text="化学竞赛一次一次失败", id="aaaaaa"),
        ActiveConcern(text="化学焦虑加重很多", id="bbbbbb"),
    ]
    clusters = _cluster_concerns_by_topic_and_people(s.state.active_concerns)
    result = ConsolidationResult(merge_groups=[
        # Short LLM prefixes (8 and 4 chars)
        _kept("concern", 1, [1, 2], ["化学竞赛", "化学"]),
    ])
    _apply_consolidation(
        s, s.km_file, s.state, result, today=1,
        memory_clusters=[], concern_clusters=clusters,
    )
    assert len(s.state.active_concerns) == 1


def test_consolidation_prefix_rejects_rewritten_opening():
    """PR5 regression: LLM rewrote the opening → reject merge. This is the
    "hallucination-guard" purpose of the prefix check."""
    s = _FakeStorage()
    s.state.active_concerns = [
        ActiveConcern(text="化学竞赛一次一次失败", id="aaaaaa"),
        ActiveConcern(text="数学焦虑加重了", id="bbbbbb"),
    ]
    clusters = _cluster_concerns_by_topic_and_people(s.state.active_concerns)
    result = ConsolidationResult(merge_groups=[
        # LLM fabricated a new summary that doesn't match either
        _kept("concern", 1, [1, 2], ["关于学习的泛泛担忧", "数学焦虑加重了"]),
    ])
    _apply_consolidation(
        s, s.km_file, s.state, result, today=1,
        memory_clusters=[], concern_clusters=clusters,
    )
    # Rewritten opening → merge rejected → both concerns survive
    assert len(s.state.active_concerns) == 2


# --- daily_highlight two-tier fallback ---


def test_highlight_grounded_returns_llm_source():
    """Baseline: well-grounded highlight survives all three checks with
    source_tag='llm' (existing behavior preserved)."""
    today_md = (
        "方语晨在走廊上跟苏念瑶八卦了沈逸凡的事情，"
        "还提到了他手机背景那只猫。"
    )
    highlight = "跟苏念瑶在走廊上聊了沈逸凡的八卦"
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
    )
    assert out == highlight
    assert tag == "llm"


def test_highlight_ungrounded_summary_grounded_uses_summary():
    """The main motivating case — 方语晨 scenario. LLM wrote a
    narrator-style highlight that fails grounding (0% overlap); summary
    is grounded. We return summary with tag 'fallback:summary' instead
    of polluting recent.md with '今天没什么戏'."""
    today_md = (
        "方语晨在走廊上跟苏念瑶八卦了沈逸凡的事情，"
        "还提到了他手机背景那只猫。"
    )
    highlight = "冬日午后望着窗外的树梢心绪万千"  # pure narrator prose
    summary = "方语晨跟苏念瑶八卦沈逸凡事情"
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
        daily_summary=summary,
    )
    assert tag == "fallback:summary"
    # Under SUMMARY_FALLBACK_MAX_LEN so no truncation
    assert out == summary


def test_highlight_and_summary_both_ungrounded_uses_generic_pool():
    """Worst case — both hallucinated. Fall through to the generic
    pool (existing behavior preserved). This is the final safety net."""
    today_md = "方语晨跟苏念瑶八卦沈逸凡"
    highlight = "冬日午后望着窗外的树梢心绪万千"
    summary = "某个遥远的地方发生了一些模糊的事情"
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
        daily_summary=summary,
    )
    assert tag == "fallback:ungrounded"
    assert out in DAILY_HIGHLIGHT_FALLBACK_POOL


def test_summary_longer_than_max_len_is_truncated():
    """A grounded summary longer than SUMMARY_FALLBACK_MAX_LEN is
    hard-truncated. We accept ugly mid-phrase cuts as the cost of keeping
    fallback content strictly more informative than '今天没什么戏' — a
    sentence-aware split on 。 is unreliable given LLM terminator noise
    ('...', ','), and the generic pool remains available as fallback."""
    today_md = "方语晨跟苏念瑶八卦沈逸凡" * 3
    highlight = "冬日午后望着窗外的树梢心绪万千"
    # 120 chars, well-grounded (same bigrams as today_md × 10)
    summary = "方语晨跟苏念瑶八卦沈逸凡" * 10
    assert len(summary) > SUMMARY_FALLBACK_MAX_LEN
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
        daily_summary=summary,
    )
    assert tag == "fallback:summary"
    assert len(out) == SUMMARY_FALLBACK_MAX_LEN


def test_empty_summary_falls_through_to_generic():
    """Missing / empty daily_summary skips the second tier entirely
    and uses the generic pool as before. Protects against LLM returning
    summary="" on a partial failure."""
    today_md = "方语晨跟苏念瑶八卦沈逸凡"
    highlight = "冬日午后望着窗外的树梢心绪万千"
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
        daily_summary="",
    )
    assert tag == "fallback:ungrounded"
    assert out in DAILY_HIGHLIGHT_FALLBACK_POOL


def test_short_summary_below_min_length_skipped():
    """Summary shorter than 10 chars (same sanity threshold highlight
    uses) is skipped. LLM occasionally returns fragment strings; a
    fragment isn't a valid highlight."""
    today_md = "方语晨跟苏念瑶八卦沈逸凡"
    highlight = "冬日午后望着窗外的树梢心绪万千"
    out, tag = _validate_daily_highlight(
        highlight, today_md, recent_md="", day=1,
        daily_summary="太短了",
    )
    assert tag == "fallback:ungrounded"
    assert out in DAILY_HIGHLIGHT_FALLBACK_POOL


def test_consolidation_concern_merge_preserves_id_history():
    """PR5: when two concerns merge, the kept concern's id_history
    accumulates the merged concern's id, so legacy [ref: id] references
    still resolve via concern_lookup's history path."""
    s = _FakeStorage()
    s.state.active_concerns = [
        ActiveConcern(text="化学竞赛失败", id="aaaaaa"),
        ActiveConcern(text="化学焦虑再一次爆发", id="bbbbbb"),
    ]
    clusters = _cluster_concerns_by_topic_and_people(s.state.active_concerns)
    result = ConsolidationResult(merge_groups=[
        _kept("concern", 1, [1, 2], ["化学竞赛失败", "化学焦虑再一次爆发"], final=7),
    ])
    _apply_consolidation(
        s, s.km_file, s.state, result, today=1,
        memory_clusters=[], concern_clusters=clusters,
    )
    assert len(s.state.active_concerns) == 1
    kept = s.state.active_concerns[0]
    assert kept.id == "aaaaaa"
    assert "bbbbbb" in kept.id_history
    assert kept.intensity == 7
