"""Base card renderer — canvas init, paper background, font loading.

Card canvas is 1080x1440 (Xiaohongshu 3:4 vertical), RGBA.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFont

from .assets import (
    FONT_LXGW_REGULAR,
    FONT_SANS_BOLD,
    FONT_SANS_REGULAR,
    FONT_SERIF_BOLD,
    FONT_SERIF_REGULAR,
)

# Canvas
CANVAS_W = 1080
CANVAS_H = 1440

# Palette (lead tones — accent/tints derived per-card)
PAPER_CREAM = (245, 239, 224, 255)       # warm off-white
PAPER_LINE = (180, 195, 215, 50)          # faint blue rule
PAPER_MARGIN_LINE = (200, 140, 130, 80)   # faint red margin
INK_BLACK = (38, 34, 30, 255)             # soft black
INK_GRAY = (110, 105, 98, 255)            # muted gray
CINNABAR_RED = (176, 40, 28, 255)         # 朱砂 seal red


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def font_wen(size: int) -> ImageFont.FreeTypeFont:
    """Primary body font — LXGW Wenkai (handwritten-leaning serif)."""
    return _font(str(FONT_LXGW_REGULAR), size)


def font_serif(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font(str(FONT_SERIF_BOLD if bold else FONT_SERIF_REGULAR), size)


def font_sans(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font(str(FONT_SANS_BOLD if bold else FONT_SANS_REGULAR), size)


def paper_background(
    width: int = CANVAS_W,
    height: int = CANVAS_H,
    line_spacing: int = 64,
    line_start_y: int = 180,
    margin_x: int = 88,
) -> Image.Image:
    """Produce a cream paper background with faint horizontal rules and a red margin.

    Uses Pillow primitives only — no external paper-texture PNG required. The
    result is the workbook look referenced in visual bible (作业本横线 + 红边距线).
    """
    img = Image.new("RGBA", (width, height), PAPER_CREAM)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img, "RGBA")

    # Horizontal rule lines
    y = line_start_y
    while y < height - 80:
        draw.line([(margin_x, y), (width - margin_x, y)], fill=PAPER_LINE, width=1)
        y += line_spacing

    # Left margin red line (subtle)
    draw.line(
        [(margin_x, line_start_y - 20), (margin_x, height - 60)],
        fill=PAPER_MARGIN_LINE,
        width=2,
    )
    return img


def save_png(img: Image.Image, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(out, format="PNG", optimize=True)
