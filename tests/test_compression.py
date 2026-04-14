"""Tests for memory compression and consolidation (PR5)."""

from pathlib import Path

from sim.memory.compression import (
    ConsolidationResult,
    MergeGroup,
    _apply_consolidation,
    _cluster_concerns_by_topic_and_people,
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
