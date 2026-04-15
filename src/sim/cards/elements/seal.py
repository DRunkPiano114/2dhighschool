"""Cinnabar-red 「班」 seal — brand mark for all cards.

Rendered procedurally so we can resize + recolor per card section. The seal
appears in two forms:
  - Small date stamp  (seal with arbitrary character/date text)
  - Brand watermark   (朱红「班」 square seal)
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..base import CINNABAR_RED, font_serif


def render_seal(
    text: str,
    size: int,
    *,
    corner_radius: int | None = None,
    fill: tuple[int, int, int, int] = CINNABAR_RED,
    font_size: int | None = None,
) -> Image.Image:
    """Return a square RGBA seal image with centered `text`.

    The seal is a rounded-square cinnabar block with reversed-out text. Used
    for the brand 「班」 mark and for small date stamps like 「第01天」.
    """
    if corner_radius is None:
        corner_radius = max(4, size // 10)
    if font_size is None:
        # Empirical scale: ~70 % of the seal side fits single-char; divide
        # by char count to fit multi-character seals like 「第001天」.
        font_size = max(12, int(size * 0.72 / max(1, len(text))))

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=corner_radius,
        fill=fill,
    )

    fnt = font_serif(font_size, bold=True)
    # Use anchor="mm" for perfect centering using font metrics.
    d.text(
        (size / 2, size / 2 + size * 0.02),
        text,
        font=fnt,
        fill=(255, 248, 238, 240),
        anchor="mm",
    )
    return img
