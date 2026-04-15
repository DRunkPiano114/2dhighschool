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
from typing import Any

from .assets import PROJECT_ROOT, load_visual_bible

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
class DailySummary:
    day: int
    headline: Beat | None
    secondaries: list[Beat] = field(default_factory=list)
    mood_map: list[MoodEntry] = field(default_factory=list)
    cp: CPPair | None = None
    golden_quote: GoldenQuote | None = None
    scene_thumbs: list[dict[str, Any]] = field(default_factory=list)


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


def build_daily_summary(day: int) -> DailySummary:
    scenes = load_day_scenes(day)
    headline = pick_headline(scenes)
    headline_thought = headline.thought if headline else None
    return DailySummary(
        day=day,
        headline=headline,
        secondaries=pick_secondaries(scenes, headline),
        mood_map=compute_mood_map(scenes),
        cp=pick_cp(scenes),
        golden_quote=pick_golden_quote(scenes, exclude_text=headline_thought),
        scene_thumbs=scene_thumbs(scenes),
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
    }
