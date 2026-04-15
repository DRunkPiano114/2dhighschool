"""Caption, hashtag and filename generators.

Pure functions — no Pillow dependency, easy to unit-test.
"""

from __future__ import annotations

from typing import Any

# Base tags that ride on every card
BASE_HASHTAGS: tuple[str, ...] = ("#SimClass", "#AI高中生", "#青春日记")

LOCATION_TAGS = {
    "教室": "#教室日常",
    "宿舍": "#宿舍夜聊",
    "操场": "#操场时光",
    "食堂": "#食堂",
    "走廊": "#走廊",
    "图书馆": "#图书馆",
    "小卖部": "#小卖部",
}

TIME_TAGS = {
    "07:00": "#早读",
    "08:45": "#课间",
    "12:00": "#午饭",
    "15:30": "#课间",
    "22:00": "#宿舍夜聊",
}


def _sanitize_filename_component(text: str) -> str:
    """Strip characters that break common filesystems."""
    bad = '<>:"/\\|?*'
    return "".join(" " if c in bad else c for c in text).strip()


def scene_filename(day: int, name: str, location: str) -> str:
    """Return a human-readable filename for a scene card download."""
    safe_name = _sanitize_filename_component(name)
    safe_loc = _sanitize_filename_component(location)
    return f"simclass_第{day:03d}天_{safe_name}@{safe_loc}.png"


def pick_hashtags(
    *,
    location: str | None,
    time: str | None,
    extra: tuple[str, ...] = (),
) -> list[str]:
    """Return hashtags: 3 base + up to 2 context-sensitive.

    Accepts None/unknown values gracefully — returns just the base set.
    """
    tags = list(BASE_HASHTAGS)
    if location:
        for key, tag in LOCATION_TAGS.items():
            if key in location:
                tags.append(tag)
                break
    if time and time in TIME_TAGS:
        t = TIME_TAGS[time]
        if t not in tags:
            tags.append(t)
    for e in extra:
        if e not in tags:
            tags.append(e)
    return tags[:5]


def scene_caption(
    *,
    day: int,
    scene_name: str,
    location: str,
    time: str,
    featured_quote: str | None,
    featured_speaker: str | None,
    motif_emoji: str = "",
) -> dict[str, Any]:
    """Build the caption payload for a scene card.

    Returned shape:
      { "caption": str, "hashtags": list[str], "filename": str }
    """
    title = f"第{day:03d}天 · {scene_name} · {location} {motif_emoji}".strip()
    body_parts = [title, ""]
    if featured_quote and featured_speaker:
        body_parts.append(f"「{featured_speaker}」{featured_quote}")
    elif featured_quote:
        body_parts.append(featured_quote)
    body_parts.append("")
    body_parts.append("SimClass · AI 班级模拟器 · 每天都在上演")
    caption = "\n".join(body_parts).strip()

    return {
        "caption": caption,
        "hashtags": pick_hashtags(location=location, time=time),
        "filename": scene_filename(day, scene_name, location),
    }
