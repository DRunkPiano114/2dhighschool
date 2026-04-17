"""Daily aggregation helpers for the 今日班级日报 card.

Pure functions that project a list of scene JSONs (one day's worth) into the
summary shape the daily card + daily JSON endpoint consume. Kept Pillow-free
so unit tests can pin the heuristics without drawing pixels.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..models.agent import Emotion
from .assets import PROJECT_ROOT, load_visual_bible
from .history import DailyHistory, load_history

DAYS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "days"


# --- Loading ---------------------------------------------------------------


def _day_dir(day: int) -> Path:
    return DAYS_DIR / f"day_{day:03d}"


def load_day_scenes(day: int) -> list[dict[str, Any]]:
    """Load every exported scene JSON for a given day, in scenes.json order."""
    dir_ = _day_dir(day)
    index_path = dir_ / "scenes.json"
    if not index_path.exists():
        raise FileNotFoundError(f"scenes.json not found for day {day}: {index_path}")
    index = json.loads(index_path.read_text("utf-8"))
    scenes: list[dict[str, Any]] = []
    for entry in index:
        sp = dir_ / entry["file"]
        if sp.exists():
            data = json.loads(sp.read_text("utf-8"))
            data.setdefault("_index_entry", entry)
            scenes.append(data)
    return scenes


# --- Name lookup -----------------------------------------------------------


def _bible_name(agent_id: str) -> str:
    bible = load_visual_bible()
    return bible.get(agent_id, {}).get("name_cn", agent_id)


def _build_name_to_id(scenes: list[dict[str, Any]]) -> dict[str, str]:
    """Build a reverse (display_name → agent_id) map from participant_names.

    Reflections reference the *other* agent by display name, not agent_id, so
    we need this map to recover CP pairs as (a_id, b_id).
    """
    mapping: dict[str, str] = {}
    for scene in scenes:
        for aid, name in (scene.get("participant_names") or {}).items():
            mapping[name] = aid
    # Also fold in the bible, which carries names for any agent ever exported.
    bible = load_visual_bible()
    for aid, cfg in bible.items():
        mapping.setdefault(cfg.get("name_cn", aid), aid)
    return mapping


# --- Data types ------------------------------------------------------------


@dataclass(frozen=True)
class Beat:
    """A single speech/thought moment suitable for headline or secondary."""

    scene_time: str
    scene_name: str
    scene_location: str
    scene_file: str
    group_index: int
    tick_index: int
    speaker_id: str
    speaker_name: str
    speech: str | None
    thought_id: str | None
    thought_name: str | None
    thought: str | None
    urgency: int


@dataclass(frozen=True)
class MoodEntry:
    agent_id: str
    agent_name: str
    dominant_emotion: str
    emotion_counts: dict[str, int]


@dataclass(frozen=True)
class CPPair:
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    favorability_delta: int
    trust_delta: int
    understanding_delta: int


@dataclass(frozen=True)
class GoldenQuote:
    agent_id: str
    agent_name: str
    text: str
    urgency: int
    scene_time: str
    scene_name: str


@dataclass(frozen=True)
class TopEventCard:
    text: str
    category: str
    scene_file: str
    scene_time: str
    scene_name: str
    witnesses: list[dict[str, str]]       # [{agent_id, agent_name}]
    non_witnesses: list[dict[str, str]]
    pull_quote: str | None
    pull_quote_agent_id: str | None
    pull_quote_agent_name: str | None
    # Scene-local coordinates of the cited tick. `进入现场` links use these to
    # land on the exact beat the card quotes, not the scene's first tick.
    group_index: int = 0
    tick_index: int = 0
    score: float = 0.0


@dataclass(frozen=True)
class ContrastCard:
    kind: Literal["mismatch", "failed_intent", "silent_judgment"]
    payload: dict[str, Any]
    score: float
    scene_time: str | None
    scene_name: str | None
    scene_file: str | None
    group_index: int = 0
    tick_index: int = 0


@dataclass(frozen=True)
class ConcernCard:
    agent_id: str
    agent_name: str
    text: str
    topic: str
    intensity: int
    reinforcement_count: int     # 0 on historical days (single-day branch)
    days_active: int             # 1 on historical days
    first_day: int               # == day on historical days
    reinforced_today: bool       # True on historical days
    score: float = 0.0


@dataclass(frozen=True)
class DailySummary:
    day: int
    headline: Beat | None
    secondaries: list[Beat] = field(default_factory=list)
    mood_map: list[MoodEntry] = field(default_factory=list)
    cp: CPPair | None = None
    golden_quote: GoldenQuote | None = None
    scene_thumbs: list[dict[str, Any]] = field(default_factory=list)
    # Phase A additions — new left-column cards.
    top_event: TopEventCard | None = None
    contrast: ContrastCard | None = None
    concern_spotlight: ConcernCard | None = None


# --- Extraction ------------------------------------------------------------


def _iter_beats(scenes: list[dict[str, Any]]):
    """Yield (scene_entry, group, tick_idx, tick) for every tick in every multi-agent group."""
    for scene in scenes:
        scene_info = scene.get("scene", {})
        entry = scene.get("_index_entry") or {}
        for g in scene.get("groups", []):
            if g.get("is_solo"):
                continue
            for ti, tick in enumerate(g.get("ticks") or []):
                yield scene_info, entry, g, ti, tick


def _beat_from(scene_info, entry, group, tick_idx, tick) -> Beat:
    speech = (tick.get("public") or {}).get("speech") or {}
    speaker_id = speech.get("agent") or ""
    speech_text = speech.get("content")

    minds = tick.get("minds") or {}
    # Thought: prefer speaker's own thought if present; else the richest thought.
    thought_id = None
    thought_text = None
    if speaker_id and speaker_id in minds:
        t = minds[speaker_id].get("inner_thought") or ""
        if t:
            thought_id = speaker_id
            thought_text = t
    if not thought_text:
        best = max(
            minds.items(),
            key=lambda kv: len(kv[1].get("inner_thought") or ""),
            default=(None, {}),
        )
        if best[0] and best[1].get("inner_thought"):
            thought_id = best[0]
            thought_text = best[1].get("inner_thought")

    urgency = max(
        (int(m.get("urgency") or 0) for m in minds.values()),
        default=0,
    )

    return Beat(
        scene_time=scene_info.get("time", ""),
        scene_name=scene_info.get("name", ""),
        scene_location=scene_info.get("location", ""),
        scene_file=entry.get("file", ""),
        group_index=group.get("group_index", 0),
        tick_index=tick_idx,
        speaker_id=speaker_id,
        speaker_name=_bible_name(speaker_id) if speaker_id else "",
        speech=speech_text,
        thought_id=thought_id,
        thought_name=_bible_name(thought_id) if thought_id else None,
        thought=thought_text,
        urgency=urgency,
    )


def _score_headline(beat: Beat) -> tuple[int, int]:
    """Headline preference: rich thought (≥15 chars) + high urgency."""
    thought_len = len(beat.thought or "")
    rich = 1 if thought_len >= 15 else 0
    return (rich, beat.urgency * 4 + thought_len)


def pick_headline(scenes: list[dict[str, Any]]) -> Beat | None:
    best: Beat | None = None
    best_score: tuple[int, int] = (-1, -1)
    for scene_info, entry, g, ti, tick in _iter_beats(scenes):
        beat = _beat_from(scene_info, entry, g, ti, tick)
        s = _score_headline(beat)
        if s > best_score:
            best_score = s
            best = beat
    return best


def pick_secondaries(
    scenes: list[dict[str, Any]],
    exclude: Beat | None,
    limit: int = 3,
) -> list[Beat]:
    """Pick `limit` additional beats — no two from the same scene as `exclude`."""
    beats: list[Beat] = []
    for scene_info, entry, g, ti, tick in _iter_beats(scenes):
        beat = _beat_from(scene_info, entry, g, ti, tick)
        if exclude and beat.scene_file == exclude.scene_file and beat.group_index == exclude.group_index and beat.tick_index == exclude.tick_index:
            continue
        beats.append(beat)

    # Sort by score descending.
    beats.sort(key=_score_headline, reverse=True)

    seen_scenes: set[str] = set()
    if exclude:
        seen_scenes.add(exclude.scene_file)
    picked: list[Beat] = []
    for b in beats:
        if b.scene_file in seen_scenes:
            continue
        seen_scenes.add(b.scene_file)
        picked.append(b)
        if len(picked) >= limit:
            break
    return picked


def compute_mood_map(scenes: list[dict[str, Any]]) -> list[MoodEntry]:
    """For each agent with any tick today, return their dominant emotion."""
    per_agent: dict[str, Counter] = defaultdict(Counter)
    for _, _, g, _, tick in _iter_beats(scenes):
        for aid, mind in (tick.get("minds") or {}).items():
            emo = mind.get("emotion")
            if emo:
                per_agent[aid][emo] += 1
    # Preserve bible ordering.
    bible = load_visual_bible()
    out: list[MoodEntry] = []
    for aid in bible.keys():
        if aid not in per_agent:
            continue
        counts = per_agent[aid]
        dominant = counts.most_common(1)[0][0]
        out.append(
            MoodEntry(
                agent_id=aid,
                agent_name=_bible_name(aid),
                dominant_emotion=dominant,
                emotion_counts=dict(counts),
            )
        )
    return out


def pick_cp(scenes: list[dict[str, Any]]) -> CPPair | None:
    """Select the two agents whose relationship moved most today.

    Sum (favorability + trust + understanding) deltas across both directions
    of each pair, then pick the pair with the largest positive combined motion.
    """
    name_to_id = _build_name_to_id(scenes)
    totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    # [fav, trust, understanding]

    for scene in scenes:
        for g in scene.get("groups", []):
            if g.get("is_solo"):
                continue
            for aid, ref in (g.get("reflections") or {}).items():
                for rc in ref.get("relationship_changes", []):
                    other_name = rc.get("to_agent")
                    other_id = name_to_id.get(other_name)
                    if not other_id:
                        continue
                    first, second = sorted((aid, other_id))
                    key: tuple[str, str] = (first, second)
                    totals[key][0] += int(rc.get("favorability") or 0)
                    totals[key][1] += int(rc.get("trust") or 0)
                    totals[key][2] += int(rc.get("understanding") or 0)

    if not totals:
        return None

    def score(kv):
        (a, b), (fav, trust, und) = kv
        return fav + trust + und

    best_pair, (fav, trust, und) = max(totals.items(), key=score)
    if fav + trust + und <= 0:
        return None
    a, b = best_pair
    return CPPair(
        a_id=a,
        a_name=_bible_name(a),
        b_id=b,
        b_name=_bible_name(b),
        favorability_delta=fav,
        trust_delta=trust,
        understanding_delta=und,
    )


def pick_golden_quote(
    scenes: list[dict[str, Any]],
    exclude_text: str | None = None,
) -> GoldenQuote | None:
    """Find the single most tweetable inner thought — urgency-weighted length.

    Pass the headline's thought via `exclude_text` so we don't surface the same
    line in both slots (the daily card reads awkwardly with duplicates).
    """
    best: tuple[int, str, str, str, str, str] | None = None  # score + data
    for scene_info, entry, g, ti, tick in _iter_beats(scenes):
        for aid, mind in (tick.get("minds") or {}).items():
            thought = mind.get("inner_thought") or ""
            if len(thought) < 8:
                continue
            if exclude_text and thought == exclude_text:
                continue
            urgency = int(mind.get("urgency") or 0)
            score = urgency * 5 + len(thought)
            if not best or score > best[0]:
                best = (
                    score,
                    aid,
                    _bible_name(aid),
                    thought,
                    scene_info.get("time", ""),
                    scene_info.get("name", ""),
                )
    if not best:
        return None
    _, aid, name, thought, st, sn = best
    return GoldenQuote(
        agent_id=aid,
        agent_name=name,
        text=thought,
        urgency=best[0],
        scene_time=st,
        scene_name=sn,
    )


# --- Phase A: left-column cards ---------------------------------------------
# Thresholds are module-level so the calibration script can reference them
# and the values can be tuned without chasing through logic. These defaults
# were picked by hand-inspecting top/threshold/bottom score buckets across
# day_001..day_009 (see scripts/calibrate_left_column.py).

TOP_EVENT_MIN_SCORE: float = 0.45
CONTRAST_MISMATCH_MIN_VALENCE_DELTA: int = 2
CONTRAST_MISMATCH_MIN_FAV_DELTA: int = 2
CONTRAST_FAILED_INTENT_MIN_URGENCY: int = 5
CONTRAST_FAILED_INTENT_MIN_REASON_LEN: int = 10
CONTRAST_SILENT_JUDGMENT_MIN_SUM: int = 3

# Whether pick_concern_spotlight applies a "last_reinforced_day >= day - 3"
# cooldown on the cross-day branch. Calibration round picked Y (no window) —
# accumulation is more emotionally load-bearing than recency, and reinforcing
# decay is already handled by the stale-concern eviction in the sim loop.
CONCERN_SPOTLIGHT_COOLDOWN_DAYS: int | None = None


_TOPIC_WEIGHT: dict[str, float] = {
    "恋爱": 2.0,
    "人际矛盾": 1.6,
    "家庭压力": 1.5,
    "自我认同": 1.3,
    "学业焦虑": 1.0,
    "未来规划": 1.0,
    "健康": 1.0,
    "兴趣爱好": 0.6,
    "期待的事": 0.6,
    "其他": 0.7,
}


# Valence table derived from the Emotion enum. `_assert_valence_exhaustive`
# below is called from tests so adding a new Emotion value trips CI
# immediately instead of silently mapping to zero.
_VALENCE_MAP: dict[str, int] = {
    "happy": +2, "touched": +2, "excited": +2, "proud": +1, "calm": +1,
    "neutral": 0, "curious": 0,
    "bored": -1, "embarrassed": -1,
    "anxious": -2, "guilty": -2, "frustrated": -2, "jealous": -2, "sad": -2,
    "angry": -3,
}


def _assert_valence_exhaustive() -> None:
    """Called from tests — fails loudly when a new Emotion value is added
    without a corresponding valence entry."""
    missing = {e.value for e in Emotion} - _VALENCE_MAP.keys()
    assert not missing, f"_VALENCE_MAP missing Emotion values: {missing}"


def _category_weight(cat: str) -> float:
    """Bucket-match weight for `new_event.category`.

    The LLM produces free-form Chinese phrases for `category` — a fixed-set
    dict lookup misses ~all entries. Keyword containment is a close-enough
    bucketing: highest weight to gossip/romance (spreads hardest), then
    conflict, social, and academic at the bottom."""
    c = cat or ""
    if any(k in c for k in ("八卦", "流言", "恋爱", "暗恋", "绯闻")):
        return 2.8
    if any(k in c for k in ("冲突", "威胁", "违纪", "纪律", "警告", "批评")):
        return 2.4
    if any(k in c for k in ("社交", "邀请", "邀约", "约定", "社交活动")):
        return 1.4
    if any(k in c for k in ("学习", "学业", "学术")):
        return 0.7
    return 1.0


def _event_score(event: dict[str, Any]) -> float:
    spread = float(event.get("spread_probability") or 0.5)
    witnesses = event.get("witnesses") or []
    return (
        spread
        * (1.0 + 0.25 * len(witnesses))
        * _category_weight(event.get("category") or "")
    )


def _fallback_event_tick(event: dict[str, Any], group: dict[str, Any]) -> int:
    """Return a sensible tick to deep-link to when the pull_quote can't be
    resolved. Walks `cite_ticks` and returns the first one that lands inside
    the group's tick range, tolerating 0/1-indexed traces the same way
    ``_pull_quote_from_group`` does. 0 only if nothing survives — better than
    dropping the cite information entirely."""
    ticks = group.get("ticks") or []
    for t_idx in event.get("cite_ticks") or []:
        for probe in (t_idx, t_idx - 1):
            if 0 <= probe < len(ticks):
                return probe
    return 0


def _pull_quote_from_group(
    group: dict[str, Any],
    event: dict[str, Any],
    name_to_id: dict[str, str],
) -> tuple[str | None, str | None, int | None]:
    """Return the best (agent_id, inner_thought, tick_idx) match for an event.

    `cite_ticks` are group-local 0-ish indices and `witnesses` are display
    names; we cross-reference to find a thought that is *from* a witness
    *during* a cited tick. If no tick/witness pair yields a thought, return
    (None, None, None) so the card degrades gracefully — pull_quote is
    decorative, not required."""
    witness_ids = {
        name_to_id[n]
        for n in event.get("witnesses") or []
        if n in name_to_id
    }
    ticks = group.get("ticks") or []
    candidates: list[tuple[int, int, str, str]] = []
    for t_idx in event.get("cite_ticks") or []:
        # cite_ticks from LLM can be 1-indexed in some traces. Accept both
        # — try the given index and (index-1), which is cheap and safe since
        # out-of-range falls through.
        for probe in (t_idx, t_idx - 1):
            if probe < 0 or probe >= len(ticks):
                continue
            for agent_id, mind in (ticks[probe].get("minds") or {}).items():
                thought = (mind.get("inner_thought") or "").strip()
                if not thought or agent_id not in witness_ids:
                    continue
                s = int(mind.get("urgency") or 0) * 4 + len(thought)
                candidates.append((s, probe, agent_id, thought))
    if not candidates:
        return (None, None, None)
    _, tick_idx, aid, thought = max(candidates)
    return (aid, thought, tick_idx)


def _iter_top_event_candidates(
    scenes: list[dict[str, Any]],
) -> list[tuple[float, dict[str, Any], int, dict[str, Any], dict[str, Any], dict[str, str]]]:
    """Enumerate (score, scene, group_index, group, event, name_to_id) for
    every new_event today. Used by `pick_top_event` and the calibration
    script."""
    name_to_id = _build_name_to_id(scenes)
    out: list[tuple[float, dict[str, Any], int, dict[str, Any], dict[str, Any], dict[str, str]]] = []
    for scene in scenes:
        for gi, group in enumerate(scene.get("groups") or []):
            for event in (group.get("narrative") or {}).get("new_events") or []:
                out.append((_event_score(event), scene, gi, group, event, name_to_id))
    return out


def pick_top_event(
    scenes: list[dict[str, Any]],
    min_score: float | None = None,
) -> TopEventCard | None:
    """Pick the single most-spread-worthy 新 event for today's 头条.

    Scores on `spread_probability × witness_count × category_weight`. Returns
    None if nothing clears `min_score` (defaults to ``TOP_EVENT_MIN_SCORE``).
    """
    threshold = TOP_EVENT_MIN_SCORE if min_score is None else min_score
    candidates = _iter_top_event_candidates(scenes)
    if not candidates:
        return None
    best = max(candidates, key=lambda t: t[0])
    score, scene, gi, group, event, name_to_id = best
    if score < threshold:
        return None

    scene_info = scene.get("scene") or {}
    entry = scene.get("_index_entry") or {}
    pull_id, pull_text, pull_tick_idx = _pull_quote_from_group(group, event, name_to_id)
    witness_names: list[str] = list(event.get("witnesses") or [])
    witness_ids: list[str] = []
    for n in witness_names:
        aid = name_to_id.get(n)
        if aid:
            witness_ids.append(aid)

    # Non-witnesses = class roster minus witnesses. Use the visual bible's
    # agent ordering so the UI lays out faces stably across days.
    bible = load_visual_bible()
    non_witness = [
        {"agent_id": aid, "agent_name": _bible_name(aid)}
        for aid in bible.keys()
        if aid not in witness_ids
    ]
    witness_payload = [
        {"agent_id": aid, "agent_name": _bible_name(aid)}
        for aid in witness_ids
    ]

    return TopEventCard(
        text=event.get("text") or "",
        category=event.get("category") or "",
        scene_file=entry.get("file") or "",
        scene_time=scene_info.get("time") or "",
        scene_name=scene_info.get("name") or "",
        witnesses=witness_payload,
        non_witnesses=non_witness,
        pull_quote=pull_text,
        pull_quote_agent_id=pull_id,
        pull_quote_agent_name=_bible_name(pull_id) if pull_id else None,
        group_index=gi,
        tick_index=pull_tick_idx if pull_tick_idx is not None else _fallback_event_tick(event, group),
        score=score,
    )


# --- Contrast: three sub-kinds -----------------------------------------------


def _agent_longest_thought(
    group: dict[str, Any], agent_id: str
) -> tuple[str, str, int]:
    """Return (emotion, longest-inner_thought, tick_idx) for a given agent
    across the group's ticks. Emotion is that agent's emotion on whichever
    tick produced the chosen thought — the one the left-column quote will
    actually show. `tick_idx` is the group-local tick index, used by
    `进入现场` to deep-link to the exact beat."""
    best_text = ""
    best_emotion = ""
    best_tick_idx = 0
    for ti, tick in enumerate(group.get("ticks") or []):
        mind = (tick.get("minds") or {}).get(agent_id) or {}
        thought = (mind.get("inner_thought") or "").strip()
        if len(thought) > len(best_text):
            best_text = thought
            best_emotion = mind.get("emotion") or ""
            best_tick_idx = ti
    return best_emotion, best_text, best_tick_idx


def _pick_mismatch_candidate(
    scenes: list[dict[str, Any]],
    name_to_id: dict[str, str],
) -> tuple[float, dict[str, Any], dict[str, Any], int, int] | None:
    """Two agents in the same group whose valences / fav-of-each-other have
    opposite signs — the 错位 card. Returns (score, scene, payload, group_index,
    tick_index) of the highest-scoring pair, or None if no pair passes the
    gate. `tick_index` is the tick at which agent A's longest thought lives,
    so `进入现场` can deep-link to that beat."""
    best: tuple[float, dict[str, Any], dict[str, Any], int, int] | None = None
    for scene in scenes:
        for gi, group in enumerate(scene.get("groups") or []):
            if group.get("is_solo"):
                continue
            reflections = group.get("reflections") or {}
            # Fav graph: (a_id → {b_id → fav})
            fav: dict[str, dict[str, int]] = defaultdict(dict)
            for aid, refl in reflections.items():
                for rc in refl.get("relationship_changes") or []:
                    bid = name_to_id.get(rc.get("to_agent") or "")
                    if not bid:
                        continue
                    fav[aid][bid] = int(rc.get("favorability") or 0)

            for aid, refl in reflections.items():
                a_emotion, a_thought, a_tick_idx = _agent_longest_thought(group, aid)
                if len(a_thought) < 12:
                    continue
                a_val = _VALENCE_MAP.get(a_emotion, 0)
                for bid in fav.get(aid, {}):
                    if bid == aid or bid not in reflections:
                        continue
                    b_emotion, b_thought, _ = _agent_longest_thought(group, bid)
                    if len(b_thought) < 12:
                        continue
                    fav_ab = fav.get(aid, {}).get(bid, 0)
                    fav_ba = fav.get(bid, {}).get(aid, 0)
                    b_val = _VALENCE_MAP.get(b_emotion, 0)
                    val_delta = abs(a_val - b_val)
                    fav_delta = abs(fav_ab - fav_ba)
                    fav_signs_differ = (fav_ab * fav_ba) < 0
                    val_signs_differ = (a_val * b_val) < 0
                    if not (fav_signs_differ or val_signs_differ):
                        continue
                    if val_delta < CONTRAST_MISMATCH_MIN_VALENCE_DELTA:
                        continue
                    if fav_delta < CONTRAST_MISMATCH_MIN_FAV_DELTA:
                        continue
                    score = float(val_delta + fav_delta)
                    # Canonicalize ordering so (a,b) and (b,a) don't both
                    # land with different scores — always pick the one with
                    # the higher a_id lexicographically first... but only
                    # once we've filtered, since the quotes differ.
                    key = (aid, bid)
                    if best is not None and best[0] >= score:
                        # still need a stable tiebreak so tests are
                        # deterministic
                        continue
                    payload = {
                        "a_id": aid,
                        "a_name": _bible_name(aid),
                        "a_thought": a_thought,
                        "a_emotion": a_emotion,
                        "b_id": bid,
                        "b_name": _bible_name(bid),
                        "b_thought": b_thought,
                        "b_emotion": b_emotion,
                        "fav_a_to_b": fav_ab,
                        "fav_b_to_a": fav_ba,
                        "_key": key,
                    }
                    best = (score, scene, payload, gi, a_tick_idx)
    return best


def _pick_failed_intent_candidate(
    scenes: list[dict[str, Any]],
) -> tuple[float, dict[str, Any], dict[str, Any], int, int] | None:
    """Single-agent failed intention — the 翻车 card. Also returns the group
    index and the tick where the agent's urgency peaked, so `进入现场` can
    deep-link to the moment that best captures the frustration."""
    best: tuple[float, dict[str, Any], dict[str, Any], int, int] | None = None
    for scene in scenes:
        for gi, group in enumerate(scene.get("groups") or []):
            if group.get("is_solo"):
                continue
            reflections = group.get("reflections") or {}
            for aid, refl in reflections.items():
                outcomes = refl.get("intention_outcomes") or []
                # urgency_proxy = max urgency this agent hit in this group,
                # and the tick at which it peaked.
                urgency_proxy = 0
                peak_tick_idx = 0
                for ti, tick in enumerate(group.get("ticks") or []):
                    mind = (tick.get("minds") or {}).get(aid) or {}
                    u = int(mind.get("urgency") or 0)
                    if u > urgency_proxy:
                        urgency_proxy = u
                        peak_tick_idx = ti
                for io in outcomes:
                    status = io.get("status") or ""
                    if status not in ("frustrated", "missed_opportunity"):
                        continue
                    reason = (io.get("brief_reason") or "").strip()
                    if len(reason) < CONTRAST_FAILED_INTENT_MIN_REASON_LEN:
                        continue
                    if urgency_proxy < CONTRAST_FAILED_INTENT_MIN_URGENCY:
                        continue
                    score = float(urgency_proxy)
                    if best is None or score > best[0]:
                        payload = {
                            "agent_id": aid,
                            "agent_name": _bible_name(aid),
                            "goal": io.get("goal") or "",
                            "status": status,
                            "brief_reason": reason,
                            "urgency_proxy": urgency_proxy,
                        }
                        best = (score, scene, payload, gi, peak_tick_idx)
    return best


def _pick_silent_judgment_candidate(
    scenes: list[dict[str, Any]],
    name_to_id: dict[str, str],
) -> tuple[float, dict[str, Any]] | None:
    """Aggregate off-stage negative favorability — the 暗戳戳 card.

    Gathers every `relationship_change` where direct_interaction is False
    and favorability is negative, groups by target agent, sums the absolute
    deltas. The winning target is the one the class is most quietly
    shit-talking.

    Cross-scene by construction — this card deliberately carries no scene
    pointer. `pick_contrast` returns `scene_*=None`, which hides the
    "进入现场" link in the UI."""
    per_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for scene in scenes:
        for group in scene.get("groups") or []:
            reflections = group.get("reflections") or {}
            for aid, refl in reflections.items():
                for rc in refl.get("relationship_changes") or []:
                    if rc.get("direct_interaction"):
                        continue
                    fav = int(rc.get("favorability") or 0)
                    if fav >= 0:
                        continue
                    target_id = name_to_id.get(rc.get("to_agent") or "")
                    if not target_id or target_id == aid:
                        continue
                    per_target[target_id].append(
                        {
                            "id": aid,
                            "name": _bible_name(aid),
                            "fav_delta": fav,
                        }
                    )

    if not per_target:
        return None

    scored: list[tuple[float, str]] = []
    for target_id, accusers in per_target.items():
        total = sum(abs(int(a["fav_delta"])) for a in accusers)
        scored.append((float(total), target_id))
    scored.sort(reverse=True)
    score, target_id = scored[0]
    if score < CONTRAST_SILENT_JUDGMENT_MIN_SUM:
        return None
    payload = {
        "target_id": target_id,
        "target_name": _bible_name(target_id),
        "accusers": per_target[target_id],
    }
    return (score, payload)


def pick_contrast(scenes: list[dict[str, Any]]) -> ContrastCard | None:
    """Pick the single highest-priority 反差 / drama card.

    Returns the first kind that passes its gate — `mismatch` > `failed_intent`
    > `silent_judgment`. The three sub-scores are on incompatible scales so
    we can't just take a global `max`; priority-by-drama-density is the
    closest approximation.
    """
    name_to_id = _build_name_to_id(scenes)

    m = _pick_mismatch_candidate(scenes, name_to_id)
    if m is not None:
        score, scene, payload, gi, tick_idx = m
        scene_info = scene.get("scene") or {}
        entry = scene.get("_index_entry") or {}
        payload = {k: v for k, v in payload.items() if not k.startswith("_")}
        return ContrastCard(
            kind="mismatch",
            payload=payload,
            score=score,
            scene_time=scene_info.get("time") or "",
            scene_name=scene_info.get("name") or "",
            scene_file=entry.get("file") or "",
            group_index=gi,
            tick_index=tick_idx,
        )
    f = _pick_failed_intent_candidate(scenes)
    if f is not None:
        score, scene, payload, gi, tick_idx = f
        scene_info = scene.get("scene") or {}
        entry = scene.get("_index_entry") or {}
        return ContrastCard(
            kind="failed_intent",
            payload=payload,
            score=score,
            scene_time=scene_info.get("time") or "",
            scene_name=scene_info.get("name") or "",
            scene_file=entry.get("file") or "",
            group_index=gi,
            tick_index=tick_idx,
        )
    s = _pick_silent_judgment_candidate(scenes, name_to_id)
    if s is not None:
        score, payload = s
        return ContrastCard(
            kind="silent_judgment",
            payload=payload,
            score=score,
            scene_time=None,
            scene_name=None,
            scene_file=None,
        )
    return None


# --- Concern spotlight -------------------------------------------------------


def _pick_single_day_concern(
    scenes: list[dict[str, Any]], day: int
) -> ConcernCard | None:
    """No persisted history — pick a concern from today's scene reflections
    (`new_concerns`). Returns a ConcernCard with reinforcement_count=0 and
    days_active=1; the UI hides the cross-day badge in that case."""
    best: tuple[float, str, dict[str, Any]] | None = None
    for scene in scenes:
        for group in scene.get("groups") or []:
            reflections = group.get("reflections") or {}
            for aid, refl in reflections.items():
                for c in refl.get("new_concerns") or []:
                    intensity = int(c.get("intensity") or 0)
                    topic = c.get("topic") or "其他"
                    weight = _TOPIC_WEIGHT.get(topic, 1.0)
                    score = intensity * weight
                    if best is None or score > best[0]:
                        best = (score, aid, c)
    if best is None:
        return None
    score, aid, c = best
    return ConcernCard(
        agent_id=aid,
        agent_name=_bible_name(aid),
        text=c.get("text") or "",
        topic=c.get("topic") or "其他",
        intensity=int(c.get("intensity") or 0),
        reinforcement_count=0,
        days_active=1,
        first_day=day,
        reinforced_today=True,
        score=score,
    )


def _pick_cross_day_concern(
    day: int, history: DailyHistory
) -> ConcernCard | None:
    """Latest-day-only: score every persisted ActiveConcern by
    ``intensity * 0.7 + reinforcement_count * 2.0`` times topic weight."""
    best: tuple[float, str, Any] | None = None
    cooldown = CONCERN_SPOTLIGHT_COOLDOWN_DAYS
    for aid, concerns in history.active_concerns_by_agent.items():
        for c in concerns:
            if cooldown is not None and c.last_reinforced_day < day - cooldown:
                continue
            topic_weight = _TOPIC_WEIGHT.get(c.topic, 1.0)
            score = (c.intensity * 0.7 + c.reinforcement_count * 2.0) * topic_weight
            if best is None or score > best[0]:
                best = (score, aid, c)
    if best is None:
        return None
    score, aid, c = best
    days_active = max(1, day - c.source_day + 1)
    return ConcernCard(
        agent_id=aid,
        agent_name=_bible_name(aid),
        text=c.text,
        topic=c.topic,
        intensity=c.intensity,
        reinforcement_count=c.reinforcement_count,
        days_active=days_active,
        first_day=c.source_day,
        reinforced_today=(c.last_reinforced_day == day),
        score=score,
    )


def pick_concern_spotlight(
    scenes: list[dict[str, Any]],
    day: int,
    history: DailyHistory | None,
) -> ConcernCard | None:
    """Pick today's "心事聚光" card.

    Historical-day / fresh-clone (history is None) → falls back to today's
    `new_concerns` with reinforcement_count=0 so the UI can hide the
    cross-day badge without breaking data. Latest-day → reads persisted
    ActiveConcerns for true cross-day continuity."""
    if history is None:
        return _pick_single_day_concern(scenes, day)
    card = _pick_cross_day_concern(day, history)
    if card is not None:
        return card
    # Persisted snapshot exists but nobody has an active concern — still
    # better to show a single-day fallback than nothing at all.
    return _pick_single_day_concern(scenes, day)


def scene_thumbs(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a lightweight thumbnail list for the landing-page scene strip."""
    thumbs: list[dict[str, Any]] = []
    for scene in scenes:
        si = scene.get("scene", {})
        entry = scene.get("_index_entry") or {}
        participants: set[str] = set()
        for g in scene.get("groups", []):
            for p in g.get("participants", []):
                participants.add(p)
        thumbs.append(
            {
                "time": si.get("time"),
                "name": si.get("name"),
                "location": si.get("location"),
                "file": entry.get("file"),
                "participants": sorted(participants),
            }
        )
    return thumbs


def build_daily_summary(
    day: int, history: DailyHistory | None = None
) -> DailySummary:
    scenes = load_day_scenes(day)
    headline = pick_headline(scenes)
    headline_thought = headline.thought if headline else None
    if history is None:
        history = load_history(up_to_day=day)
    return DailySummary(
        day=day,
        headline=headline,
        secondaries=pick_secondaries(scenes, headline),
        mood_map=compute_mood_map(scenes),
        cp=pick_cp(scenes),
        golden_quote=pick_golden_quote(scenes, exclude_text=headline_thought),
        scene_thumbs=scene_thumbs(scenes),
        top_event=pick_top_event(scenes),
        contrast=pick_contrast(scenes),
        concern_spotlight=pick_concern_spotlight(scenes, day, history),
    )


# --- JSON serializer for API ----------------------------------------------


def _beat_dict(b: Beat | None) -> dict[str, Any] | None:
    if b is None:
        return None
    return {
        "scene_time": b.scene_time,
        "scene_name": b.scene_name,
        "scene_location": b.scene_location,
        "scene_file": b.scene_file,
        "group_index": b.group_index,
        "tick_index": b.tick_index,
        "speaker_id": b.speaker_id,
        "speaker_name": b.speaker_name,
        "speech": b.speech,
        "thought_id": b.thought_id,
        "thought_name": b.thought_name,
        "thought": b.thought,
        "urgency": b.urgency,
    }


def summary_to_dict(s: DailySummary) -> dict[str, Any]:
    bible = load_visual_bible()
    return {
        "day": s.day,
        "headline": _beat_dict(s.headline),
        "secondaries": [_beat_dict(b) for b in s.secondaries],
        "mood_map": [
            {
                "agent_id": m.agent_id,
                "agent_name": m.agent_name,
                "dominant_emotion": m.dominant_emotion,
                "emotion_counts": m.emotion_counts,
                "main_color": bible.get(m.agent_id, {}).get("main_color", "#666"),
                "motif_emoji": bible.get(m.agent_id, {}).get("motif_emoji", ""),
            }
            for m in s.mood_map
        ],
        "cp": None if s.cp is None else {
            "a_id": s.cp.a_id,
            "a_name": s.cp.a_name,
            "b_id": s.cp.b_id,
            "b_name": s.cp.b_name,
            "favorability_delta": s.cp.favorability_delta,
            "trust_delta": s.cp.trust_delta,
            "understanding_delta": s.cp.understanding_delta,
        },
        "golden_quote": None if s.golden_quote is None else {
            "agent_id": s.golden_quote.agent_id,
            "agent_name": s.golden_quote.agent_name,
            "text": s.golden_quote.text,
            "scene_time": s.golden_quote.scene_time,
            "scene_name": s.golden_quote.scene_name,
        },
        "scene_thumbs": s.scene_thumbs,
        "top_event": None if s.top_event is None else {
            "text": s.top_event.text,
            "category": s.top_event.category,
            "scene_file": s.top_event.scene_file,
            "scene_time": s.top_event.scene_time,
            "scene_name": s.top_event.scene_name,
            "witnesses": s.top_event.witnesses,
            "non_witnesses": s.top_event.non_witnesses,
            "pull_quote": s.top_event.pull_quote,
            "pull_quote_agent_id": s.top_event.pull_quote_agent_id,
            "pull_quote_agent_name": s.top_event.pull_quote_agent_name,
            "group_index": s.top_event.group_index,
            "tick_index": s.top_event.tick_index,
        },
        "contrast": None if s.contrast is None else {
            "kind": s.contrast.kind,
            "payload": s.contrast.payload,
            "scene_time": s.contrast.scene_time,
            "scene_name": s.contrast.scene_name,
            "scene_file": s.contrast.scene_file,
            "group_index": s.contrast.group_index,
            "tick_index": s.contrast.tick_index,
        },
        "concern_spotlight": None if s.concern_spotlight is None else {
            "agent_id": s.concern_spotlight.agent_id,
            "agent_name": s.concern_spotlight.agent_name,
            "text": s.concern_spotlight.text,
            "topic": s.concern_spotlight.topic,
            "intensity": s.concern_spotlight.intensity,
            "reinforcement_count": s.concern_spotlight.reinforcement_count,
            "days_active": s.concern_spotlight.days_active,
            "first_day": s.concern_spotlight.first_day,
            "reinforced_today": s.concern_spotlight.reinforced_today,
        },
    }
