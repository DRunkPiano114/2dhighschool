"""Copy selected LimeZu animated spritesheets into canon/ and emit a manifest.

LimeZu animated sheets are horizontal frame strips: image width = frame_w *
frame_count, height = frame_h. Per-sprite frame size depends on the object
bounding box (varies per object), so we record it explicitly here.

Each sprite produces:
  canon/animated/<name>.png         — the full sheet (untouched)
  canon/animated/manifest.json      — {name: {frame_w, frame_h, count, fps}}

Re-run after editing `ANIMATED`.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from sim.cards.assets import ASSETS_DIR  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "canon" / "animated"
SRC = ASSETS_DIR / "moderninteriors-win" / "3_Animated_objects" / "32x32" / "spritesheets"

# (file, name, frame_w, frame_h, fps)
# frame_w/h in pixels. Reading each sheet's total width lets us infer count.
ANIMATED: list[tuple[str, str, int, int, int]] = [
    # Tall pendulum clock — 128×96 sheet → 4 frames of 32×96 (1 tile wide × 3 tall)
    ("animated_pendulum_clock_32x32.png", "pendulum_clock", 32, 96, 3),
    # Old TV on stand — 384×64 sheet → 6 frames of 64×64 (2×2) judging from
    # the preview showing 6 discrete TVs.
    ("animated_old_tv_32x32.png", "old_tv", 64, 64, 4),
    # Canteen fridge with cake — 384×96 → 12 frames of 32×96 (1×3 tiles).
    ("animated_canteen_fridge_cake_1_32x32.png", "fridge_cake", 32, 96, 4),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clean previous output so removed entries don't linger.
    for p in OUT_DIR.glob("*.png"):
        p.unlink()
    manifest: dict[str, dict[str, int]] = {}
    for file, name, fw, fh, fps in ANIMATED:
        src = SRC / file
        if not src.exists():
            print(f"  ✗ {name}: missing {file}")
            continue
        img = Image.open(src)
        w, h = img.size
        if w % fw != 0 or h != fh:
            print(f"  ! {name}: sheet {w}×{h} doesn't divide evenly by frame {fw}×{fh}")
        count = w // fw
        dst = OUT_DIR / f"{name}.png"
        shutil.copy(src, dst)
        manifest[name] = {"frame_w": fw, "frame_h": fh, "count": count, "fps": fps}
        print(f"  ✓ {name:<20} {count} frames of {fw}×{fh} @ {fps}fps")

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  manifest.json ({len(manifest)} animated sprites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
