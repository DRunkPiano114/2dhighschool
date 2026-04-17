"""Daily card — 1080×1440 班级日报 summary for a single day.

Layered like scene_card:
  - Data is gathered by `aggregations.build_daily_summary(day)` (pure).
  - Rendering reads the dataclasses and draws Pillow primitives.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .aggregations import (
    ConcernCard,
    ContrastCard,
    DailySummary,
    TopEventCard,
    build_daily_summary,
)
from .assets import load_visual_bible
from .base import (
    CANVAS_H,
    CANVAS_W,
    INK_BLACK,
    INK_GRAY,
    font_serif,
    font_wen,
    paper_background,
)
from .elements.balloon import render_balloon
from .elements.banner import draw_divider
from .elements.portrait import scaled_portrait
from .elements.seal import render_seal


def _draw_section_title(draw: ImageDraw.ImageDraw, x: int, y: int, label: str) -> None:
    fnt = font_serif(28, bold=True)
    draw.text((x, y), label, font=fnt, fill=INK_BLACK)


def _wrap_cjk(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Char-by-char CJK wrap, same algorithm as balloon._wrap_cjk."""
    lines: list[str] = []
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            lines.append(buf)
            buf = ""
            i += 1
            continue
        candidate = buf + ch
        if font.getlength(candidate) <= max_width:
            buf = candidate
            i += 1
        else:
            if buf:
                lines.append(buf)
                buf = ""
            else:
                lines.append(ch)
                i += 1
    if buf:
        lines.append(buf)
    return lines


def _draw_tag(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    fill: tuple[int, int, int, int],
    *,
    fg: tuple[int, int, int, int] = (255, 248, 232, 255),
    font_size: int = 20,
    pad_x: int = 12,
    pad_y: int = 4,
) -> int:
    """Draw a pill tag. Returns the x-position just past the tag (for chaining)."""
    fnt = font_wen(font_size)
    tw = int(fnt.getlength(text))
    box_w = tw + 2 * pad_x
    box_h = int(fnt.getmetrics()[0] + fnt.getmetrics()[1]) + 2 * pad_y
    draw.rounded_rectangle(
        [(x, y), (x + box_w, y + box_h)],
        radius=6,
        fill=fill,
        outline=fill,
    )
    draw.text((x + pad_x, y + pad_y - 2), text, font=fnt, fill=fg)
    return x + box_w


def _category_tone(category: str) -> tuple[int, int, int, int]:
    c = category or ""
    if any(k in c for k in ("八卦", "流言", "恋爱", "暗恋", "绯闻")):
        return (192, 92, 128, 255)
    if any(k in c for k in ("冲突", "威胁", "违纪", "纪律", "警告", "批评")):
        return (176, 60, 48, 255)
    if any(k in c for k in ("社交", "邀请", "邀约", "约定", "社交活动")):
        return (96, 130, 170, 255)
    if any(k in c for k in ("学习", "学业", "学术")):
        return (120, 130, 90, 255)
    return (130, 115, 95, 255)


_TOPIC_COLORS: dict[str, tuple[int, int, int, int]] = {
    "恋爱": (214, 76, 122, 255),
    "人际矛盾": (181, 75, 53, 255),
    "家庭压力": (148, 102, 53, 255),
    "自我认同": (106, 85, 155, 255),
    "学业焦虑": (62, 125, 179, 255),
    "未来规划": (47, 138, 115, 255),
    "健康": (77, 143, 74, 255),
    "兴趣爱好": (166, 126, 40, 255),
    "期待的事": (166, 126, 40, 255),
    "其他": (119, 119, 119, 255),
}


_CONTRAST_TAG_COLOR: dict[str, tuple[int, int, int, int]] = {
    "mismatch": (155, 95, 140, 255),
    "failed_intent": (165, 95, 70, 255),
    "silent_judgment": (130, 120, 100, 255),
}


_CONTRAST_TAG_LABEL: dict[str, str] = {
    "mismatch": "错位",
    "failed_intent": "今日翻车",
    "silent_judgment": "暗戳戳",
}


def _render_mood_strip(
    img: Image.Image,
    y: int,
    summary: DailySummary,
    *,
    margin: int = 88,
) -> None:
    """Tiny color-chip strip: one dot per agent tinted by their main color."""
    if not summary.mood_map:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "心情地图")
    bible = load_visual_bible()
    chip_y = y + 38
    chip_r = 26
    gap = 16
    n = len(summary.mood_map)
    total_w = n * (chip_r * 2) + (n - 1) * gap
    start_x = max(margin, (CANVAS_W - total_w) // 2)
    name_fnt = font_wen(18)
    for i, entry in enumerate(summary.mood_map):
        cx = start_x + chip_r + i * (chip_r * 2 + gap)
        cy = chip_y + chip_r
        hex_ = bible.get(entry.agent_id, {}).get("main_color", "#888888")
        color = _hex_to_rgba(hex_, alpha=240)
        draw.ellipse(
            [(cx - chip_r, cy - chip_r), (cx + chip_r, cy + chip_r)],
            fill=color,
            outline=INK_BLACK,
            width=2,
        )
        draw.text(
            (cx, cy + chip_r + 8),
            entry.agent_name,
            font=name_fnt,
            fill=INK_GRAY,
            anchor="mt",
        )


def _hex_to_rgba(hex_str: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (r, g, b, alpha)


def _render_cp_block(img: Image.Image, y: int, summary: DailySummary, *, margin: int = 88) -> int:
    if summary.cp is None:
        return y
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "今日 CP")
    cp = summary.cp
    # Two small portraits side by side with a red heart between.
    portrait_size = 140
    a = scaled_portrait(cp.a_id, portrait_size)
    b = scaled_portrait(cp.b_id, portrait_size)
    row_y = y + 50
    img.paste(a, (margin, row_y), a)
    img.paste(b, (margin + portrait_size + 90, row_y), b)
    heart_fnt = font_serif(60, bold=True)
    draw.text(
        (margin + portrait_size + 45, row_y + portrait_size // 2),
        "♥",
        font=heart_fnt,
        fill=(176, 40, 28, 255),
        anchor="mm",
    )
    name_fnt = font_serif(24, bold=True)
    draw.text(
        (margin + portrait_size // 2, row_y + portrait_size + 8),
        cp.a_name,
        font=name_fnt,
        fill=INK_BLACK,
        anchor="mt",
    )
    draw.text(
        (margin + portrait_size + 90 + portrait_size // 2, row_y + portrait_size + 8),
        cp.b_name,
        font=name_fnt,
        fill=INK_BLACK,
        anchor="mt",
    )
    delta_fnt = font_wen(20)
    draw.text(
        (margin, row_y + portrait_size + 50),
        f"好感 +{cp.favorability_delta}  信任 +{cp.trust_delta}  理解 +{cp.understanding_delta}",
        font=delta_fnt,
        fill=INK_GRAY,
    )
    return row_y + portrait_size + 90


def _render_quote_block(
    img: Image.Image,
    y: int,
    summary: DailySummary,
    *,
    margin: int = 88,
) -> int:
    if summary.golden_quote is None:
        return y
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "今日金句")
    quote = summary.golden_quote
    bal = render_balloon(
        f"（{quote.agent_name}）{quote.text}",
        max_width=CANVAS_W - 2 * margin,
        kind="thought",
        font_size=30,
    )
    img.paste(bal, (margin, y + 40), bal)
    return y + 40 + bal.height + 12


def _render_headline_block(
    img: Image.Image,
    y: int,
    summary: DailySummary,
    *,
    margin: int = 88,
) -> int:
    """Legacy fallback — kept for when `top_event` is absent."""
    h = summary.headline
    if h is None:
        return y
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "今日头条")

    meta_fnt = font_wen(22)
    draw.text(
        (margin, y + 34),
        f"{h.scene_time}  ·  {h.scene_name}  ·  {h.scene_location}",
        font=meta_fnt,
        fill=INK_GRAY,
    )

    body_start_y = y + 66
    if h.speech:
        bal = render_balloon(
            f"{h.speaker_name}：{h.speech}",
            max_width=CANVAS_W - 2 * margin,
            kind="speech",
            font_size=28,
        )
        img.paste(bal, (margin, body_start_y), bal)
        body_start_y += bal.height + 12
    if h.thought:
        bal = render_balloon(
            f"（{h.thought_name or h.speaker_name} 心想）{h.thought}",
            max_width=CANVAS_W - 2 * margin,
            kind="thought",
            font_size=26,
        )
        img.paste(bal, (margin, body_start_y), bal)
        body_start_y += bal.height + 12
    return body_start_y


def _render_top_event_block(
    img: Image.Image,
    y: int,
    event: TopEventCard,
    *,
    margin: int = 88,
) -> int:
    """Headline-style card driven by TopEventCard. Title + category tag +
    scene meta + body text + optional pull-quote."""
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "今日头条")

    tag = event.category or "事件"
    _draw_tag(draw, margin + 180, y + 4, tag, _category_tone(tag))

    meta_fnt = font_wen(22)
    draw.text(
        (margin, y + 40),
        f"{event.scene_time} · {event.scene_name}",
        font=meta_fnt,
        fill=INK_GRAY,
    )

    body_fnt = font_serif(26, bold=True)
    cur_y = y + 76
    if event.text:
        for line in _wrap_cjk(event.text, body_fnt, CANVAS_W - 2 * margin):
            draw.text((margin, cur_y), line, font=body_fnt, fill=INK_BLACK)
            cur_y += 36

    if event.pull_quote:
        speaker = event.pull_quote_agent_name or ""
        prefix = f"「{speaker}」" if speaker else ""
        bal = render_balloon(
            f"{prefix}{event.pull_quote}",
            max_width=CANVAS_W - 2 * margin,
            kind="thought",
            font_size=24,
            pad_x=22,
            pad_y=16,
        )
        img.paste(bal, (margin, cur_y + 8), bal)
        cur_y += 8 + bal.height
    return cur_y + 6


def _render_contrast_block(
    img: Image.Image,
    y: int,
    contrast: ContrastCard,
    *,
    margin: int = 88,
) -> int:
    """Render 今日对照 card for mismatch / failed_intent / silent_judgment."""
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "今日对照")

    tag_color = _CONTRAST_TAG_COLOR.get(contrast.kind, (130, 120, 100, 255))
    tag_label = _CONTRAST_TAG_LABEL.get(contrast.kind, "对照")
    _draw_tag(draw, margin + 180, y + 4, tag_label, tag_color)

    payload = contrast.payload or {}
    cur_y = y + 44

    if contrast.kind == "mismatch":
        col_w = (CANVAS_W - 2 * margin - 32) // 2
        a_name = str(payload.get("a_name") or "")
        a_thought = str(payload.get("a_thought") or "")
        b_name = str(payload.get("b_name") or "")
        b_thought = str(payload.get("b_thought") or "")
        a_bal = render_balloon(
            f"{a_name}：{a_thought}" if a_thought else a_name,
            max_width=col_w,
            kind="thought",
            font_size=22,
            pad_x=18,
            pad_y=14,
        )
        b_bal = render_balloon(
            f"{b_name}：{b_thought}" if b_thought else b_name,
            max_width=col_w,
            kind="thought",
            font_size=22,
            pad_x=18,
            pad_y=14,
        )
        img.paste(a_bal, (margin, cur_y), a_bal)
        img.paste(b_bal, (margin + col_w + 32, cur_y), b_bal)
        cur_y += max(a_bal.height, b_bal.height)
    elif contrast.kind == "failed_intent":
        name = str(payload.get("agent_name") or "")
        goal = str(payload.get("goal") or "")
        status = str(payload.get("status") or "")
        reason = str(payload.get("brief_reason") or "")
        status_label = "受挫" if status == "frustrated" else "错过时机"
        hdr_fnt = font_serif(26, bold=True)
        draw.text(
            (margin, cur_y),
            f"{name}：想 {goal} → 却 {status_label}",
            font=hdr_fnt,
            fill=INK_BLACK,
        )
        cur_y += 40
        if reason:
            r_fnt = font_wen(22)
            for line in _wrap_cjk(reason, r_fnt, CANVAS_W - 2 * margin):
                draw.text((margin, cur_y), line, font=r_fnt, fill=INK_GRAY)
                cur_y += 30
    elif contrast.kind == "silent_judgment":
        target = str(payload.get("target_name") or "")
        accusers = payload.get("accusers") or []
        hdr_fnt = font_serif(26, bold=True)
        draw.text(
            (margin, cur_y),
            f"{target} 背后被扣分",
            font=hdr_fnt,
            fill=INK_BLACK,
        )
        cur_y += 40
        if accusers:
            names = "、".join(str(a.get("name") or "") for a in accusers[:5])
            extra = "" if len(accusers) <= 5 else f" 等 {len(accusers)} 人"
            sub_fnt = font_wen(22)
            draw.text(
                (margin, cur_y),
                f"由 {names}{extra} 背后扣分",
                font=sub_fnt,
                fill=INK_GRAY,
            )
            cur_y += 30
    return cur_y + 8


def _render_concern_block(
    img: Image.Image,
    y: int,
    concern: ConcernCard,
    *,
    margin: int = 88,
) -> int:
    """Render 心事聚光 — portrait + agent name + topic tag + text + intensity."""
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_section_title(draw, margin, y, "心事聚光")

    try:
        portrait = scaled_portrait(concern.agent_id, 72)
        img.paste(portrait, (margin, y + 42), portrait)
        text_x = margin + 92
    except FileNotFoundError:
        text_x = margin

    name_fnt = font_serif(24, bold=True)
    draw.text((text_x, y + 48), concern.agent_name, font=name_fnt, fill=INK_BLACK)
    name_w = int(name_fnt.getlength(concern.agent_name))

    topic = concern.topic or "其他"
    topic_color = _TOPIC_COLORS.get(topic, _TOPIC_COLORS["其他"])
    _draw_tag(draw, text_x + name_w + 14, y + 50, topic, topic_color)

    text_fnt = font_wen(22)
    cur_y = y + 92
    if concern.text:
        for line in _wrap_cjk(concern.text, text_fnt, CANVAS_W - text_x - margin):
            draw.text((text_x, cur_y), line, font=text_fnt, fill=INK_BLACK)
            cur_y += 30

    # Intensity bar (10 cells)
    bar_label_fnt = font_wen(18)
    draw.text(
        (text_x, cur_y + 4),
        f"强度 {concern.intensity}/10",
        font=bar_label_fnt,
        fill=INK_GRAY,
    )
    bar_x = text_x + 100
    bar_y = cur_y + 10
    cell_w = 16
    cell_gap = 4
    for i in range(10):
        cx = bar_x + i * (cell_w + cell_gap)
        color = topic_color if i < concern.intensity else (200, 190, 170, 255)
        draw.rectangle([(cx, bar_y), (cx + cell_w, bar_y + 14)], fill=color)
    return cur_y + 40


def _render_card(summary: DailySummary) -> Image.Image:
    img = paper_background(CANVAS_W, CANVAS_H)
    draw = ImageDraw.Draw(img, "RGBA")

    # Header: big date seal + title
    seal = render_seal(f"第{summary.day:03d}天", size=138, font_size=34)
    img.paste(seal, (72, 60), seal)

    title_fnt = font_serif(60, bold=True)
    sub_fnt = font_wen(30)
    draw.text((232, 72), "班级日报", font=title_fnt, fill=INK_BLACK)
    draw.text((232, 150), "一天里的教室、宿舍、操场与心事", font=sub_fnt, fill=INK_GRAY)

    draw_divider(img, y=218, x_start=72, x_end=CANVAS_W - 72, color=INK_GRAY, dash=10)

    y = 240
    if summary.top_event is not None:
        y = _render_top_event_block(img, y, summary.top_event)
    else:
        y = _render_headline_block(img, y, summary)
    y += 10

    if summary.contrast is not None:
        y = _render_contrast_block(img, y, summary.contrast)
    else:
        y = _render_quote_block(img, y, summary)
    y += 8

    if summary.concern_spotlight is not None:
        y = _render_concern_block(img, y, summary.concern_spotlight)
        y += 8

    _render_mood_strip(img, y + 6, summary)
    y += 128
    y = _render_cp_block(img, y, summary)

    # Footer: brand
    draw_divider(img, y=CANVAS_H - 150, x_start=72, x_end=CANVAS_W - 72, color=INK_GRAY, dash=10)
    brand = render_seal("班", size=120, font_size=80)
    img.paste(brand, (CANVAS_W - 72 - 120, CANVAS_H - 72 - 120), brand)
    draw.text(
        (90, CANVAS_H - 120),
        "SimCampus · AI 校园模拟器",
        font=font_serif(32, bold=True),
        fill=INK_BLACK,
    )
    draw.text(
        (90, CANVAS_H - 80),
        "每天都在上演",
        font=font_wen(26),
        fill=INK_GRAY,
    )
    return img


def render(day: int) -> Image.Image:
    summary = build_daily_summary(day)
    return _render_card(summary)
