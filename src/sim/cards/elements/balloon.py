"""Speech + thought balloons with CJK text wrapping."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from ..base import INK_BLACK, INK_GRAY, font_wen


# Balloon palettes (RGBA)
SPEECH_FILL = (255, 253, 246, 240)          # near-white, warm
SPEECH_BORDER = (80, 70, 58, 200)
THOUGHT_FILL = (235, 228, 245, 235)         # soft lavender — inner-voice mark
THOUGHT_BORDER = (140, 120, 165, 180)


def _wrap_cjk(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap CJK+ASCII text to fit within `max_width` px.

    CJK has no word boundaries, so wrapping is char-by-char. ASCII runs are
    grouped so we don't split an English word mid-character.
    """
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
                # Single char exceeds width — force it
                lines.append(ch)
                i += 1
    if buf:
        lines.append(buf)
    return lines


def render_balloon(
    text: str,
    *,
    max_width: int,
    kind: str = "speech",
    font_size: int = 32,
    pad_x: int = 28,
    pad_y: int = 22,
    line_spacing: int = 10,
    tail: str | None = None,
) -> Image.Image:
    """Render a speech or thought balloon as a standalone RGBA image.

    kind: "speech" (rounded rect + pointy tail) | "thought" (rounded rect,
    slightly softer palette, italic-feeling via LXGW Wenkai). Tail direction
    is controlled by `tail`: 'bl' | 'br' | None.
    """
    fnt = font_wen(font_size)
    text_max = max_width - 2 * pad_x
    lines = _wrap_cjk(text, fnt, text_max)

    # Measure
    ascent, descent = fnt.getmetrics()
    line_h = ascent + descent
    line_widths = [fnt.getlength(l) for l in lines]
    text_w = max(line_widths) if line_widths else 0
    text_h = line_h * len(lines) + line_spacing * max(0, len(lines) - 1)

    box_w = int(text_w + 2 * pad_x)
    box_h = int(text_h + 2 * pad_y)

    # Leave room for tail if requested
    tail_h = 28 if tail else 0
    img = Image.new("RGBA", (box_w, box_h + tail_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    if kind == "thought":
        fill, border = THOUGHT_FILL, THOUGHT_BORDER
    else:
        fill, border = SPEECH_FILL, SPEECH_BORDER

    radius = 22
    d.rounded_rectangle(
        [(0, 0), (box_w - 1, box_h - 1)],
        radius=radius,
        fill=fill,
        outline=border,
        width=2,
    )

    # Tail
    if tail == "bl":
        tx = 44
        d.polygon(
            [(tx, box_h - 2), (tx + 28, box_h - 2), (tx + 6, box_h + tail_h - 2)],
            fill=fill,
            outline=border,
        )
        # Re-stroke inner edge to hide border overlap with box bottom
        d.line([(tx, box_h - 2), (tx + 28, box_h - 2)], fill=fill, width=3)
    elif tail == "br":
        tx = box_w - 72
        d.polygon(
            [(tx, box_h - 2), (tx + 28, box_h - 2), (tx + 22, box_h + tail_h - 2)],
            fill=fill,
            outline=border,
        )
        d.line([(tx, box_h - 2), (tx + 28, box_h - 2)], fill=fill, width=3)

    # Text
    text_color = INK_BLACK if kind == "speech" else INK_GRAY
    y = pad_y
    for line in lines:
        d.text((pad_x, y), line, font=fnt, fill=text_color)
        y += line_h + line_spacing

    return img
