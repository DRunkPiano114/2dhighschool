"""Banners, dividers, header rules."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..base import INK_GRAY


def draw_divider(
    img: Image.Image,
    *,
    y: int,
    x_start: int,
    x_end: int,
    dash: int = 8,
    gap: int = 6,
    color: tuple[int, int, int, int] = INK_GRAY,
    width: int = 2,
) -> None:
    """Draw a dashed horizontal divider onto `img` (mutates in place)."""
    d = ImageDraw.Draw(img, "RGBA")
    x = x_start
    while x < x_end:
        x2 = min(x + dash, x_end)
        d.line([(x, y), (x2, y)], fill=color, width=width)
        x = x2 + gap
