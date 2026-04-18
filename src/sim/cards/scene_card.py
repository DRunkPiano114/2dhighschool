"""Scene card projection — raw scene JSON → LayoutSpec → dict for the frontend.

Two layers, both pure:
  1. Selection (`select_featured_group`, `_pick_featured_tick_index`) — heuristics
     that pick which group + tick a share card should anchor on.
  2. LayoutSpec (`scene_to_layout_spec`) — dataclass capturing exactly what the
     frontend <SceneShareCard> needs to render. `spec_to_dict` serializes it
     for `share_tick_layouts[]` in the exported scene JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .assets import PROJECT_ROOT, load_visual_bible

DAYS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "days"

# Portrait + bubble caps. Groups of ≤4 get everyone on the card (fits cleanly
# at 1080 width). Groups of 5+ fall back to the speaker/target/top-witness
# summary so the card doesn't turn into a crowded thumbnail grid.
def _portrait_cap_for(n_participants: int) -> int:
    return 4 if n_participants <= 4 else 3


def _witness_bubble_cap_for(n_participants: int) -> int:
    # Speaker speech + target thought occupy 2 bubble slots; remaining slots go
    # to witnesses by urgency. 4-person → 2 witness bubbles, 5+ → 1.
    return max(1, _portrait_cap_for(n_participants) - 2)


# --- Data loading ----------------------------------------------------------


def day_dir(day: int) -> Path:
    return DAYS_DIR / f"day_{day:03d}"


def load_scenes_index(day: int) -> list[dict[str, Any]]:
    path = day_dir(day) / "scenes.json"
    if not path.exists():
        raise FileNotFoundError(f"scenes.json not found for day {day}: {path}")
    return json.loads(path.read_text("utf-8"))


def load_scene_by_array_index(day: int, scene_idx: int) -> dict[str, Any]:
    """Load a scene by its position in scenes.json (0-based).

    The frontend navigates by array position (scenes.json entries can carry
    non-sequential `scene_index` fields); the export mirrors that contract.
    """
    index = load_scenes_index(day)
    if scene_idx < 0 or scene_idx >= len(index):
        raise IndexError(
            f"scene_idx {scene_idx} out of range for day {day} "
            f"(have {len(index)} scenes)"
        )
    entry = index[scene_idx]
    path = day_dir(day) / entry["file"]
    if not path.exists():
        raise FileNotFoundError(f"scene file not found: {path}")
    return json.loads(path.read_text("utf-8"))


# --- Selection (pure) ------------------------------------------------------


def select_featured_group(scene_data: dict[str, Any]) -> int | None:
    """Pick the most dramatically loaded multi-agent group in the scene.

    Rules (matching the plan):
      1. Filter to multi-agent groups (is_solo=False or no is_solo field +
         multiple participants).
      2. Rank by sum(tick.urgency) + sum(len(inner_thought)) across all ticks.
      3. If no multi-agent group exists, return None (caller should treat as
         "no scene card" — solo reflections belong on the agent card).
    """
    candidates: list[tuple[int, int]] = []  # (score, group_index)
    for idx, group in enumerate(scene_data.get("groups", [])):
        if group.get("is_solo"):
            continue
        if len(group.get("participants", [])) < 2:
            continue
        ticks = group.get("ticks") or []
        if not ticks:
            continue
        score = 0
        for tick in ticks:
            minds = tick.get("minds") or {}
            for mind in minds.values():
                score += int(mind.get("urgency") or 0)
                score += len(mind.get("inner_thought") or "")
        candidates.append((score, idx))

    if not candidates:
        return None
    # Highest score; ties broken by earliest group_index for determinism.
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][1]


def _pick_featured_tick_index(group: dict[str, Any]) -> int | None:
    """Choose the tick inside the group with the strongest beat.

    Prefers: tick that has public speech AND at least one rich inner thought
    (≥ 12 chars). Falls back to highest aggregate urgency. Returns the index
    into group['ticks']; None if no ticks.
    """
    ticks = group.get("ticks") or []
    if not ticks:
        return None

    def score(indexed: tuple[int, dict[str, Any]]) -> tuple[int, int, int, int]:
        _, tick = indexed
        has_speech = bool((tick.get("public") or {}).get("speech"))
        minds = tick.get("minds") or {}
        rich_thoughts = sum(
            1 for m in minds.values() if len(m.get("inner_thought") or "") >= 12
        )
        urgency_sum = sum(int(m.get("urgency") or 0) for m in minds.values())
        # Tie-break on earliest tick for determinism.
        return (int(has_speech), rich_thoughts, urgency_sum, -indexed[0])

    best = max(enumerate(ticks), key=score)
    return best[0]


# --- LayoutSpec ------------------------------------------------------------


@dataclass(frozen=True)
class BubbleSpec:
    agent_id: str
    display_name: str
    kind: str  # "speech" | "thought"
    text: str


@dataclass(frozen=True)
class LayoutSpec:
    """Everything the frontend renderer needs, derived purely from scene data."""

    day: int
    time: str
    scene_name: str
    location: str
    # Ordered portraits: speaker first, target second, witness third.
    portraits: list[tuple[str, str]] = field(default_factory=list)  # (agent_id, name_cn)
    bubbles: list[BubbleSpec] = field(default_factory=list)
    featured_quote: str | None = None  # strongest inner thought, for caption
    featured_speaker_name: str | None = None
    # Group-local index of the tick this layout was projected from. None only
    # when the group has no ticks at all (header-only card).
    tick_index: int | None = None


def _group_display_name(
    agent_id: str,
    participant_names: dict[str, str],
    bible: dict[str, Any],
) -> str:
    if agent_id in participant_names:
        return participant_names[agent_id]
    visual = bible.get(agent_id, {})
    return visual.get("name_cn", agent_id)


def scene_to_layout_spec(
    scene_data: dict[str, Any],
    group_index: int,
    tick_index: int | None = None,
) -> LayoutSpec:
    """Project a scene + group + tick into a render-ready dataclass.

    ``tick_index`` selects which tick in the group anchors the card. When
    ``None``, falls back to ``_pick_featured_tick_index`` (server-side best
    pick). The frontend passes the user's currently-viewed tick so 保存图
    matches what the user is reading.
    """
    bible = load_visual_bible()
    scene = scene_data["scene"]
    participant_names = scene_data.get("participant_names", {})
    group = scene_data["groups"][group_index]
    ticks = group.get("ticks") or []

    portraits: list[tuple[str, str]] = []
    bubbles: list[BubbleSpec] = []
    featured_quote: str | None = None
    featured_speaker_name: str | None = None

    if tick_index is not None and 0 <= tick_index < len(ticks):
        resolved_index: int | None = tick_index
    else:
        resolved_index = _pick_featured_tick_index(group)

    if resolved_index is None:
        # No ticks — unusual but possible. Card still renders header + empty.
        return LayoutSpec(
            day=scene["day"],
            time=scene["time"],
            scene_name=scene["name"],
            location=scene["location"],
        )
    tick = ticks[resolved_index]

    speech = (tick.get("public") or {}).get("speech") or {}
    speaker_id = speech.get("agent")
    target_id = speech.get("target")
    speech_text = speech.get("content") or ""

    minds = tick.get("minds") or {}

    # Ordered portraits: speaker, target, top witness (not speaker/target).
    used: set[str] = set()
    ordered: list[str] = []
    if speaker_id and speaker_id in group.get("participants", []):
        ordered.append(speaker_id)
        used.add(speaker_id)
    if target_id and target_id in group.get("participants", []) and target_id not in used:
        ordered.append(target_id)
        used.add(target_id)

    participants = group.get("participants", [])
    portrait_cap = _portrait_cap_for(len(participants))
    witness_cap = _witness_bubble_cap_for(len(participants))

    witness_candidates = [
        (aid, m)
        for aid, m in minds.items()
        if aid not in used and m.get("inner_thought")
    ]
    witness_candidates.sort(
        key=lambda item: int(item[1].get("urgency") or 0),
        reverse=True,
    )
    for aid, _ in witness_candidates:
        if len(ordered) >= portrait_cap:
            break
        ordered.append(aid)
        used.add(aid)

    # Fill remaining slots from other participants (keeps the card populated
    # even when there's no rich inner monologue).
    for aid in participants:
        if len(ordered) >= portrait_cap:
            break
        if aid not in used:
            ordered.append(aid)
            used.add(aid)

    portraits = [
        (aid, _group_display_name(aid, participant_names, bible))
        for aid in ordered[:portrait_cap]
    ]

    # Bubbles: speech from speaker, thought from target (if present), thought
    # from witness (if present).
    if speaker_id and speech_text:
        bubbles.append(
            BubbleSpec(
                agent_id=speaker_id,
                display_name=_group_display_name(speaker_id, participant_names, bible),
                kind="speech",
                text=speech_text,
            )
        )

    if target_id and target_id in minds:
        t_thought = minds[target_id].get("inner_thought")
        if t_thought:
            bubbles.append(
                BubbleSpec(
                    agent_id=target_id,
                    display_name=_group_display_name(target_id, participant_names, bible),
                    kind="thought",
                    text=t_thought,
                )
            )

    for aid, _ in witness_candidates[:witness_cap]:
        w_thought = minds[aid].get("inner_thought")
        if w_thought:
            bubbles.append(
                BubbleSpec(
                    agent_id=aid,
                    display_name=_group_display_name(aid, participant_names, bible),
                    kind="thought",
                    text=w_thought,
                )
            )

    # Featured quote = strongest inner_thought by (urgency, length).
    thought_ranking = sorted(
        ((aid, m) for aid, m in minds.items() if m.get("inner_thought")),
        key=lambda item: (
            int(item[1].get("urgency") or 0),
            len(item[1].get("inner_thought") or ""),
        ),
        reverse=True,
    )
    if thought_ranking:
        aid, m = thought_ranking[0]
        featured_quote = m.get("inner_thought")
        featured_speaker_name = _group_display_name(aid, participant_names, bible)

    return LayoutSpec(
        day=scene["day"],
        time=scene["time"],
        scene_name=scene["name"],
        location=scene["location"],
        portraits=portraits,
        bubbles=bubbles,
        featured_quote=featured_quote,
        featured_speaker_name=featured_speaker_name,
        tick_index=resolved_index,
    )


# --- JSON serialization for frontend-rendered share cards ------------------


def spec_to_dict(spec: LayoutSpec) -> dict[str, Any]:
    """Serialize a LayoutSpec for consumption by the frontend <SceneShareCard>.

    Python is the source of truth for scene selection/ordering logic (featured
    tick pick, portrait ordering, bubble choice, featured_quote). The frontend
    never recomputes these — it renders this dict directly. Each portrait
    carries motif_emoji + motif_tag inline so the TS side doesn't need to
    join against visual_bible.json.
    """
    bible = load_visual_bible()
    return {
        "day": spec.day,
        "time": spec.time,
        "scene_name": spec.scene_name,
        "location": spec.location,
        "portraits": [
            {
                "agent_id": aid,
                "name_cn": name_cn,
                "motif_emoji": bible.get(aid, {}).get("motif_emoji", ""),
                "motif_tag": bible.get(aid, {}).get("motif_tag", ""),
            }
            for aid, name_cn in spec.portraits
        ],
        "bubbles": [
            {
                "agent_id": b.agent_id,
                "display_name": b.display_name,
                "kind": b.kind,
                "text": b.text,
            }
            for b in spec.bubbles
        ],
        "featured_quote": spec.featured_quote,
        "featured_speaker_name": spec.featured_speaker_name,
        "tick_index": spec.tick_index,
    }
