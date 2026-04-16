"""Split a labeled sheet into horizontal bands of N tile rows each, for
viewing-friendly sizes. Outputs <stem>_band_NN.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    src = Path(sys.argv[1])
    rows_per_band = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    img = Image.open(src)
    tile_h = 32 * scale
    total_rows = img.height // tile_h
    for start in range(0, total_rows, rows_per_band):
        end = min(start + rows_per_band, total_rows)
        crop = img.crop((0, start * tile_h, img.width, end * tile_h))
        out = src.parent / f"{src.stem}_r{start:02d}_{end:02d}.png"
        crop.save(out)
        print(f"  {out.name}  rows {start}..{end-1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
