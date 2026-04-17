"""One-shot calibration tool for the daily-report left-column thresholds.

Runs pick_top_event / pick_contrast / pick_concern_spotlight with gating
disabled across every exported day, dumps CSVs and a bucketed preview.md so
the threshold and concern-cooldown defaults in aggregations.py can be
eyeballed against real data.

Usage:
    uv run python scripts/calibrate_left_column.py [--out-dir DIR]

Outputs (default: .cache/left_column_calibration/):
    top_event.csv            every new_event with its score
    contrast_mismatch.csv    every same-group valence/fav contrast pair
    contrast_failed.csv      every failed intention outcome
    contrast_silent.csv      every (target, Σ fav_delta) silent judgment
    concern_cross_day.csv    every active concern from persisted state
    concern_single_day.csv   every today-only new_concern
    preview.md               top-10 / threshold-zone-10 / bottom-10 per card
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sim.cards.aggregations import (  # noqa: E402
    CONTRAST_FAILED_INTENT_MIN_REASON_LEN,
    CONTRAST_FAILED_INTENT_MIN_URGENCY,
    CONTRAST_MISMATCH_MIN_FAV_DELTA,
    CONTRAST_MISMATCH_MIN_VALENCE_DELTA,
    CONTRAST_SILENT_JUDGMENT_MIN_SUM,
    TOP_EVENT_MIN_SCORE,
    _TOPIC_WEIGHT,
    _VALENCE_MAP,
    _agent_longest_thought,
    _bible_name,
    _build_name_to_id,
    _event_score,
    _pull_quote_from_group,
    load_day_scenes,
)
from sim.cards.history import DailyHistory, _latest_simulated_day, load_history  # noqa: E402


DAYS_DIR = ROOT / "web" / "public" / "data" / "days"


def _exported_days() -> list[int]:
    if not DAYS_DIR.exists():
        return []
    out: list[int] = []
    for p in sorted(DAYS_DIR.glob("day_*")):
        if p.is_dir():
            try:
                out.append(int(p.name.split("_", 1)[1]))
            except (ValueError, IndexError):
                continue
    return sorted(out)


# --- Row types -------------------------------------------------------------


@dataclass
class TopEventRow:
    day: int
    score: float
    category: str
    spread: float
    witnesses: int
    text: str


@dataclass
class MismatchRow:
    day: int
    score: float
    val_delta: int
    fav_delta: int
    a_name: str
    a_emotion: str
    b_name: str
    b_emotion: str
    fav_ab: int
    fav_ba: int
    a_thought: str
    b_thought: str


@dataclass
class FailedIntentRow:
    day: int
    score: float
    agent_name: str
    status: str
    goal: str
    brief_reason: str
    urgency: int


@dataclass
class SilentJudgmentRow:
    day: int
    score: float
    target_name: str
    accuser_count: int
    accuser_names: str


@dataclass
class ConcernRow:
    day: int
    kind: str      # "cross_day" or "single_day"
    score: float
    agent_name: str
    topic: str
    intensity: int
    reinforcement_count: int
    days_active: int
    text: str


# --- Enumerators -----------------------------------------------------------


def _enumerate_top_events(day: int, scenes: list[dict[str, Any]]) -> list[TopEventRow]:
    rows: list[TopEventRow] = []
    for scene in scenes:
        for group in scene.get("groups") or []:
            for event in (group.get("narrative") or {}).get("new_events") or []:
                rows.append(
                    TopEventRow(
                        day=day,
                        score=_event_score(event),
                        category=event.get("category") or "",
                        spread=float(event.get("spread_probability") or 0),
                        witnesses=len(event.get("witnesses") or []),
                        text=event.get("text") or "",
                    )
                )
    return rows


def _enumerate_mismatches(
    day: int, scenes: list[dict[str, Any]]
) -> list[MismatchRow]:
    rows: list[MismatchRow] = []
    name_to_id = _build_name_to_id(scenes)
    for scene in scenes:
        for group in scene.get("groups") or []:
            if group.get("is_solo"):
                continue
            reflections = group.get("reflections") or {}
            fav: dict[str, dict[str, int]] = defaultdict(dict)
            for aid, refl in reflections.items():
                for rc in refl.get("relationship_changes") or []:
                    bid = name_to_id.get(rc.get("to_agent") or "")
                    if bid:
                        fav[aid][bid] = int(rc.get("favorability") or 0)
            seen: set[tuple[str, str]] = set()
            for aid, refl in reflections.items():
                a_emo, a_thought = _agent_longest_thought(group, aid)
                if len(a_thought) < 12:
                    continue
                for bid in fav.get(aid, {}):
                    if bid == aid or bid not in reflections:
                        continue
                    sorted_pair = sorted((aid, bid))
                    key = (sorted_pair[0], sorted_pair[1])
                    if key in seen:
                        continue
                    seen.add(key)
                    b_emo, b_thought = _agent_longest_thought(group, bid)
                    if len(b_thought) < 12:
                        continue
                    fav_ab = fav.get(aid, {}).get(bid, 0)
                    fav_ba = fav.get(bid, {}).get(aid, 0)
                    a_val = _VALENCE_MAP.get(a_emo, 0)
                    b_val = _VALENCE_MAP.get(b_emo, 0)
                    val_delta = abs(a_val - b_val)
                    fav_delta = abs(fav_ab - fav_ba)
                    score = float(val_delta + fav_delta)
                    rows.append(
                        MismatchRow(
                            day=day,
                            score=score,
                            val_delta=val_delta,
                            fav_delta=fav_delta,
                            a_name=_bible_name(aid),
                            a_emotion=a_emo,
                            b_name=_bible_name(bid),
                            b_emotion=b_emo,
                            fav_ab=fav_ab,
                            fav_ba=fav_ba,
                            a_thought=a_thought,
                            b_thought=b_thought,
                        )
                    )
    return rows


def _enumerate_failed_intents(
    day: int, scenes: list[dict[str, Any]]
) -> list[FailedIntentRow]:
    rows: list[FailedIntentRow] = []
    for scene in scenes:
        for group in scene.get("groups") or []:
            if group.get("is_solo"):
                continue
            reflections = group.get("reflections") or {}
            for aid, refl in reflections.items():
                outcomes = refl.get("intention_outcomes") or []
                urgency_proxy = 0
                for tick in group.get("ticks") or []:
                    mind = (tick.get("minds") or {}).get(aid) or {}
                    urgency_proxy = max(urgency_proxy, int(mind.get("urgency") or 0))
                for io in outcomes:
                    status = io.get("status") or ""
                    if status not in ("frustrated", "missed_opportunity"):
                        continue
                    rows.append(
                        FailedIntentRow(
                            day=day,
                            score=float(urgency_proxy),
                            agent_name=_bible_name(aid),
                            status=status,
                            goal=io.get("goal") or "",
                            brief_reason=io.get("brief_reason") or "",
                            urgency=urgency_proxy,
                        )
                    )
    return rows


def _enumerate_silent_judgments(
    day: int, scenes: list[dict[str, Any]]
) -> list[SilentJudgmentRow]:
    name_to_id = _build_name_to_id(scenes)
    per_target: dict[str, list[tuple[str, int]]] = defaultdict(list)
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
                    per_target[target_id].append((aid, fav))
    rows: list[SilentJudgmentRow] = []
    for target_id, accusers in per_target.items():
        total = sum(abs(f) for _, f in accusers)
        rows.append(
            SilentJudgmentRow(
                day=day,
                score=float(total),
                target_name=_bible_name(target_id),
                accuser_count=len(accusers),
                accuser_names=", ".join(_bible_name(a) for a, _ in accusers),
            )
        )
    return rows


def _enumerate_concerns(
    day: int,
    scenes: list[dict[str, Any]],
    history: DailyHistory | None,
    *,
    include_cooldown_variants: bool = True,
) -> list[ConcernRow]:
    rows: list[ConcernRow] = []

    if history is not None:
        for aid, concerns in history.active_concerns_by_agent.items():
            for c in concerns:
                weight = _TOPIC_WEIGHT.get(c.topic, 1.0)
                score = (c.intensity * 0.7 + c.reinforcement_count * 2.0) * weight
                kind = "cross_day"
                if include_cooldown_variants and (c.last_reinforced_day < day - 3):
                    kind = "cross_day_outside_3d_window"
                rows.append(
                    ConcernRow(
                        day=day,
                        kind=kind,
                        score=score,
                        agent_name=_bible_name(aid),
                        topic=c.topic,
                        intensity=c.intensity,
                        reinforcement_count=c.reinforcement_count,
                        days_active=max(1, day - c.source_day + 1),
                        text=c.text,
                    )
                )

    # Always enumerate single-day too, so the preview can compare.
    for scene in scenes:
        for group in scene.get("groups") or []:
            reflections = group.get("reflections") or {}
            for aid, refl in reflections.items():
                for c in refl.get("new_concerns") or []:
                    topic = c.get("topic") or "其他"
                    intensity = int(c.get("intensity") or 0)
                    weight = _TOPIC_WEIGHT.get(topic, 1.0)
                    rows.append(
                        ConcernRow(
                            day=day,
                            kind="single_day",
                            score=intensity * weight,
                            agent_name=_bible_name(aid),
                            topic=topic,
                            intensity=intensity,
                            reinforcement_count=0,
                            days_active=1,
                            text=c.get("text") or "",
                        )
                    )
    return rows


# --- CSV / preview emitters ------------------------------------------------


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _bucket_sample(rows: list[Any], key, threshold: float) -> dict[str, list[Any]]:
    """Return top/threshold-zone/bottom samples. `key` extracts a score from
    each row. Threshold-zone is the 10 rows nearest to `threshold`."""
    ordered = sorted(rows, key=key, reverse=True)
    top = ordered[:10]
    bottom = list(reversed(ordered[-10:]))
    with_dist = sorted(ordered, key=lambda r: abs(key(r) - threshold))
    threshold_zone = with_dist[:10]
    return {"top10": top, "threshold10": threshold_zone, "bottom10": bottom}


def _md_section(
    title: str,
    buckets: dict[str, list[Any]],
    describe,
) -> str:
    lines = [f"## {title}", ""]
    for bucket_name in ("top10", "threshold10", "bottom10"):
        lines.append(f"### {bucket_name}")
        if not buckets[bucket_name]:
            lines.append("_(empty)_")
        for row in buckets[bucket_name]:
            lines.append(f"- {describe(row)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / ".cache" / "left_column_calibration",
        help="output directory (default: .cache/left_column_calibration/)",
    )
    args = parser.parse_args()

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    days = _exported_days()
    if not days:
        print("No exported days under web/public/data/days/. Run `uv run sim` first.")
        return

    latest = _latest_simulated_day() or max(days)
    print(f"Calibrating across days {days[0]}..{days[-1]} (latest={latest}).")

    all_top: list[TopEventRow] = []
    all_mm: list[MismatchRow] = []
    all_fi: list[FailedIntentRow] = []
    all_sj: list[SilentJudgmentRow] = []
    all_cn: list[ConcernRow] = []

    for day in days:
        scenes = load_day_scenes(day)
        history = load_history(up_to_day=day)
        all_top.extend(_enumerate_top_events(day, scenes))
        all_mm.extend(_enumerate_mismatches(day, scenes))
        all_fi.extend(_enumerate_failed_intents(day, scenes))
        all_sj.extend(_enumerate_silent_judgments(day, scenes))
        all_cn.extend(_enumerate_concerns(day, scenes, history))

    # CSVs.
    _write_csv(
        out / "top_event.csv",
        ["day", "score", "category", "spread", "witnesses", "text"],
        [[r.day, f"{r.score:.3f}", r.category, r.spread, r.witnesses, r.text] for r in all_top],
    )
    _write_csv(
        out / "contrast_mismatch.csv",
        ["day", "score", "val_delta", "fav_delta", "a_name", "a_emotion", "b_name", "b_emotion", "fav_ab", "fav_ba", "a_thought", "b_thought"],
        [
            [r.day, r.score, r.val_delta, r.fav_delta, r.a_name, r.a_emotion, r.b_name, r.b_emotion, r.fav_ab, r.fav_ba, r.a_thought, r.b_thought]
            for r in all_mm
        ],
    )
    _write_csv(
        out / "contrast_failed.csv",
        ["day", "score", "agent_name", "status", "goal", "brief_reason", "urgency"],
        [[r.day, r.score, r.agent_name, r.status, r.goal, r.brief_reason, r.urgency] for r in all_fi],
    )
    _write_csv(
        out / "contrast_silent.csv",
        ["day", "score", "target_name", "accuser_count", "accuser_names"],
        [[r.day, r.score, r.target_name, r.accuser_count, r.accuser_names] for r in all_sj],
    )
    _write_csv(
        out / "concerns.csv",
        ["day", "kind", "score", "agent_name", "topic", "intensity", "reinforcement_count", "days_active", "text"],
        [
            [r.day, r.kind, f"{r.score:.3f}", r.agent_name, r.topic, r.intensity, r.reinforcement_count, r.days_active, r.text]
            for r in all_cn
        ],
    )

    # preview.md
    md_parts: list[str] = [
        f"# Left-column calibration preview",
        f"Days covered: {days[0]}–{days[-1]} ({len(days)} days). Latest simulated: day {latest}.",
        "",
        "Thresholds in use:",
        "",
        f"- `TOP_EVENT_MIN_SCORE` = {TOP_EVENT_MIN_SCORE}",
        f"- mismatch: |val_delta| ≥ {CONTRAST_MISMATCH_MIN_VALENCE_DELTA}, |fav_delta| ≥ {CONTRAST_MISMATCH_MIN_FAV_DELTA}",
        f"- failed_intent: urgency ≥ {CONTRAST_FAILED_INTENT_MIN_URGENCY}, brief_reason len ≥ {CONTRAST_FAILED_INTENT_MIN_REASON_LEN}",
        f"- silent_judgment: Σ|fav_delta| ≥ {CONTRAST_SILENT_JUDGMENT_MIN_SUM}",
        "",
    ]
    md_parts.append(
        _md_section(
            "Top event (score = spread × (1+0.25·witnesses) × cat_weight)",
            _bucket_sample(all_top, lambda r: r.score, TOP_EVENT_MIN_SCORE),
            lambda r: f"`score={r.score:.2f}` day={r.day} cat={r.category!r} W={r.witnesses} S={r.spread} — {r.text}",
        )
    )
    md_parts.append(
        _md_section(
            "Contrast · mismatch (val_delta + fav_delta)",
            _bucket_sample(
                all_mm,
                lambda r: r.score,
                float(CONTRAST_MISMATCH_MIN_VALENCE_DELTA + CONTRAST_MISMATCH_MIN_FAV_DELTA),
            ),
            lambda r: f"`score={r.score:.1f}` day={r.day} {r.a_name}({r.a_emotion}) ↔ {r.b_name}({r.b_emotion}) · fav({r.fav_ab}/{r.fav_ba}) · {r.a_thought[:25]}… / {r.b_thought[:25]}…",
        )
    )
    md_parts.append(
        _md_section(
            "Contrast · failed_intent (urgency proxy)",
            _bucket_sample(all_fi, lambda r: r.score, float(CONTRAST_FAILED_INTENT_MIN_URGENCY)),
            lambda r: f"`score={r.score:.1f}` day={r.day} {r.agent_name} · {r.status} · {r.goal} · {r.brief_reason}",
        )
    )
    md_parts.append(
        _md_section(
            "Contrast · silent_judgment (Σ|fav_delta|)",
            _bucket_sample(all_sj, lambda r: r.score, float(CONTRAST_SILENT_JUDGMENT_MIN_SUM)),
            lambda r: f"`score={r.score:.1f}` day={r.day} target={r.target_name} · {r.accuser_count} accusers ({r.accuser_names})",
        )
    )

    # Concern variants — split cross-day (all, and within 3d window) vs
    # single-day so we can eyeball which bucket is more emotionally
    # load-bearing. Plan A-0: decide whether to apply the 3-day cooldown.
    cross = [r for r in all_cn if r.kind.startswith("cross_day")]
    single = [r for r in all_cn if r.kind == "single_day"]
    within_3d = [r for r in cross if r.kind == "cross_day"]
    outside_3d = [r for r in cross if r.kind == "cross_day_outside_3d_window"]

    md_parts.append(
        _md_section(
            "Concern · cross-day, last_reinforced_day within 3d (variant X)",
            _bucket_sample(within_3d, lambda r: r.score, 6.0),
            lambda r: f"`score={r.score:.2f}` day={r.day} {r.agent_name} · {r.topic} · I={r.intensity} RC={r.reinforcement_count} DA={r.days_active} — {r.text}",
        )
    )
    md_parts.append(
        _md_section(
            "Concern · cross-day, outside 3d window (would be hidden by variant X)",
            _bucket_sample(outside_3d, lambda r: r.score, 6.0),
            lambda r: f"`score={r.score:.2f}` day={r.day} {r.agent_name} · {r.topic} · I={r.intensity} RC={r.reinforcement_count} DA={r.days_active} — {r.text}",
        )
    )
    md_parts.append(
        _md_section(
            "Concern · single-day (new_concerns today — historical days use this)",
            _bucket_sample(single, lambda r: r.score, 6.0),
            lambda r: f"`score={r.score:.2f}` day={r.day} {r.agent_name} · {r.topic} · I={r.intensity} — {r.text}",
        )
    )

    (out / "preview.md").write_text("\n".join(md_parts), encoding="utf-8")

    print(f"Wrote {out}:")
    for p in sorted(out.iterdir()):
        print(f"  {p.relative_to(out)}")
    # silence unused-imports on _pull_quote_from_group (exposed for future
    # extension of the script without re-importing)
    _ = _pull_quote_from_group


if __name__ == "__main__":
    main()
