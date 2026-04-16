"""Draw a red 32×32 tile grid + (col,row) numbering on a LimeZu sheet so we
can pick furniture coordinates by eye without miscounting.

Usage:
    uv run python scripts/label_sheet.py <sheet_path> <out_path> [--scale N]

Defaults to 3× upscale for readability. Output is a PNG with tile labels at
every 2nd row/col to avoid clutter.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw, ImageFont


def label(sheet_path: Path, out_path: Path, scale: int = 3) -> None:
    src = Image.open(sheet_path).convert("RGBA")
    w, h = src.size
    # Nearest-neighbor upscale keeps pixel art crisp.
    img = src.resize((w * scale, h * scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(img)
    tile = 32 * scale
    cols, rows = w // 32, h // 32

    # Grid lines — every tile in thin red, every 4th tile in thicker red.
    for c in range(cols + 1):
        x = c * tile
        width = 2 if c % 4 else 3
        color = (255, 0, 0, 180) if c % 4 else (255, 0, 0, 255)
        draw.line([(x, 0), (x, h * scale)], fill=color, width=width)
    for r in range(rows + 1):
        y = r * tile
        width = 2 if r % 4 else 3
        color = (255, 0, 0, 180) if r % 4 else (255, 0, 0, 255)
        draw.line([(0, y), (w * scale, y)], fill=color, width=width)

    # Labels at every 2nd tile: "c,r" in the top-left corner.
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", max(12, scale * 5))
    except OSError:
        font = ImageFont.load_default()
    for r in range(0, rows, 2):
        for c in range(0, cols, 2):
            x, y = c * tile + 3, r * tile + 1
            # Black outline for visibility on bright/dark bg.
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x + dx, y + dy), f"{c},{r}", fill=(0, 0, 0, 255), font=font)
            draw.text((x, y), f"{c},{r}", fill=(255, 255, 0, 255), font=font)

    img.save(out_path)
    print(f"  ✓ {out_path}  ({cols}×{rows} tiles, scale={scale}×)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sheet", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--scale", type=int, default=3)
    a = p.parse_args()
    label(a.sheet, a.out, a.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
