"""Agent archive card projection — 累计成长模式.

Day N's agent card shows the agent as they are at the end of Day N: cumulative
emotion, top relationships, recent memories, active concerns, and a featured
inner thought from the day. Reuses `build_context_at_timepoint` so all the
snapshot-loading, today-so-far, and qualitative-label logic is shared with
the chat/role-play endpoints. `spec_to_dict` serializes the layout for the
frontend <AgentShareCard> to render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..agent.storage import WorldStorage
from ..api.context import build_context_at_timepoint
from .aggregations import load_day_scenes
from .assets import get_agent_visual

# Agent cards are rendered using the 22:00 end-of-day snapshot.
AGENT_TIME_PERIOD = "22:00"

# Chinese labels for emotion enum values — backend ships raw English from the
# Emotion enum, but a share card is end-user-facing so it gets the display text
# here. Keep in sync with web/src/lib/constants.ts::EMOTION_LABELS.
EMOTION_LABELS_CN: dict[str, str] = {
    "happy": "开心",
    "sad": "难过",
    "anxious": "焦虑",
    "angry": "生气",
    "excited": "兴奋",
    "calm": "平静",
    "embarrassed": "尴尬",
    "bored": "无聊",
    "neutral": "平常",
    "jealous": "嫉妒",
    "proud": "自豪",
    "guilty": "愧疚",
    "frustrated": "挫败",
    "touched": "感动",
    "curious": "好奇",
}


def _emotion_cn(raw: str) -> str:
    return EMOTION_LABELS_CN.get(raw, raw)


# --- Data types ------------------------------------------------------------


@dataclass(frozen=True)
class RelationshipPreview:
    target_name: str
    favorability: int
    trust: int
    label_text: str


@dataclass(frozen=True)
class MemoryPreview:
    date: str
    text: str
    importance: int


@dataclass(frozen=True)
class ConcernPreview:
    text: str
    intensity_label: str
    positive: bool


@dataclass(frozen=True)
class AgentLayoutSpec:
    """Render-ready snapshot of one agent on one day."""

    agent_id: str
    name_cn: str
    day: int
    is_teacher: bool
    motif_emoji: str
    motif_tag: str
    main_color: str
    emotion_label: str
    energy_label: str
    pressure_label: str
    featured_quote: str | None
    featured_scene: str | None
    relationships: list[RelationshipPreview] = field(default_factory=list)
    memories: list[MemoryPreview] = field(default_factory=list)
    top_concern: ConcernPreview | None = None
    self_narrative: str = ""


# --- Pure projection -------------------------------------------------------


def _featured_quote_for(agent_id: str, day: int) -> tuple[str | None, str | None]:
    """Walk the day's scenes, pick the agent's strongest inner thought."""
    try:
        scenes = load_day_scenes(day)
    except FileNotFoundError:
        return None, None

    best: tuple[int, str, str] | None = None  # (score, thought, scene_label)
    for scene in scenes:
        sinfo = scene.get("scene", {})
        label = f"{sinfo.get('time', '')} · {sinfo.get('name', '')}"
        for g in scene.get("groups", []):
            if g.get("is_solo"):
                refl = g.get("solo_reflection", {}) or {}
                thought = refl.get("inner_thought", "")
                if agent_id in g.get("participants", []) and thought:
                    score = len(thought) + 4  # solo thoughts lack urgency; weight them lightly
                    if not best or score > best[0]:
                        best = (score, thought, label)
                continue
            for tick in g.get("ticks", []) or []:
                mind = (tick.get("minds") or {}).get(agent_id)
                if not mind:
                    continue
                thought = mind.get("inner_thought", "")
                if len(thought) < 10:
                    continue
                urgency = int(mind.get("urgency") or 0)
                score = urgency * 5 + len(thought)
                if not best or score > best[0]:
                    best = (score, thought, label)
    if not best:
        return None, None
    _, thought, label = best
    return thought, label


def context_to_agent_spec(
    agent_id: str,
    day: int,
    ctx: dict[str, Any],
    featured_quote: str | None,
    featured_scene: str | None,
) -> AgentLayoutSpec:
    """Project chat-context dict → render-ready dataclass."""
    visual = get_agent_visual(agent_id)
    is_teacher = bool(visual.get("is_teacher"))

    # Top 3 relationships by favorability, only for students (teacher card
    # omits CP/relationship section).
    rels: list[RelationshipPreview] = []
    if not is_teacher:
        raw = sorted(
            ctx.get("relationships", []),
            key=lambda r: int(r.get("favorability") or 0),
            reverse=True,
        )[:3]
        for r in raw:
            rels.append(
                RelationshipPreview(
                    target_name=r.get("target_name", ""),
                    favorability=int(r.get("favorability") or 0),
                    trust=int(r.get("trust") or 0),
                    label_text=r.get("label_text", ""),
                )
            )

    # Top 2 key memories by importance (already sorted by build_context…).
    mems: list[MemoryPreview] = []
    for m in ctx.get("key_memories", [])[:2]:
        if hasattr(m, "model_dump"):
            m = m.model_dump()
        mems.append(
            MemoryPreview(
                date=str(m.get("date", "")),
                text=str(m.get("text", "")),
                importance=int(m.get("importance") or 0),
            )
        )

    # Top active concern (intensity already labeled in context).
    concerns_raw = ctx.get("active_concerns", [])
    top_concern: ConcernPreview | None = None
    if concerns_raw:
        def intensity_sort_key(c):
            return int(c.get("intensity") or 0)
        strongest = max(concerns_raw, key=intensity_sort_key)
        top_concern = ConcernPreview(
            text=str(strongest.get("text", "")),
            intensity_label=str(strongest.get("intensity_label", "")),
            positive=bool(strongest.get("positive")),
        )

    return AgentLayoutSpec(
        agent_id=agent_id,
        name_cn=visual.get("name_cn", agent_id),
        day=day,
        is_teacher=is_teacher,
        motif_emoji=visual.get("motif_emoji", ""),
        motif_tag=visual.get("motif_tag", ""),
        main_color=visual.get("main_color", "#888888"),
        emotion_label=_emotion_cn(str(ctx.get("emotion_label", ""))),
        energy_label=str(ctx.get("energy_label", "")),
        pressure_label=str(ctx.get("pressure_label", "")),
        featured_quote=featured_quote,
        featured_scene=featured_scene,
        relationships=rels,
        memories=mems,
        top_concern=top_concern,
        self_narrative=str(ctx.get("self_narrative", "")),
    )


def build_agent_spec(
    agent_id: str,
    day: int,
    world: WorldStorage,
) -> AgentLayoutSpec:
    """Public entry: world + agent + day → render-ready dataclass."""
    ctx = build_context_at_timepoint(agent_id, day, AGENT_TIME_PERIOD, world)
    quote, scene_label = _featured_quote_for(agent_id, day)
    return context_to_agent_spec(agent_id, day, ctx, quote, scene_label)


# --- JSON serialization for frontend-rendered share cards ------------------


def spec_to_dict(spec: AgentLayoutSpec) -> dict[str, Any]:
    return {
        "agent_id": spec.agent_id,
        "name_cn": spec.name_cn,
        "day": spec.day,
        "is_teacher": spec.is_teacher,
        "motif_emoji": spec.motif_emoji,
        "motif_tag": spec.motif_tag,
        "main_color": spec.main_color,
        "emotion_label": spec.emotion_label,
        "energy_label": spec.energy_label,
        "pressure_label": spec.pressure_label,
        "featured_quote": spec.featured_quote,
        "featured_scene": spec.featured_scene,
        "relationships": [
            {
                "target_name": r.target_name,
                "favorability": r.favorability,
                "trust": r.trust,
                "label_text": r.label_text,
            }
            for r in spec.relationships
        ],
        "memories": [
            {"date": m.date, "text": m.text, "importance": m.importance}
            for m in spec.memories
        ],
        "top_concern": None if spec.top_concern is None else {
            "text": spec.top_concern.text,
            "intensity_label": spec.top_concern.intensity_label,
            "positive": spec.top_concern.positive,
        },
        "self_narrative": spec.self_narrative,
    }
