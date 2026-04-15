"""Generate per-agent portrait PNGs from LimeZu premade sprite sheets.

Idempotent: produces byte-identical output on re-runs. Reads `data/visual_bible.json`
and writes one `data/portraits/{agent_id}.png` per agent.

Portrait composition (per agent):
  1. Crop the premade sprite sheet at `crop` coordinates (32x48 head+torso).
  2. Scale 4x using NEAREST (preserves pixel-art look, avoids blur).
  3. Composite onto a circular background tinted with `main_color`.
  4. Save as RGBA PNG.

Re-run after changing sprite_source or crop in visual_bible.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow "uv run python scripts/generate_portraits.py" from project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw

from sim.cards.assets import (
    PORTRAITS_DIR,
    SPRITE_SHEETS_DIR,
    load_visual_bible,
)

SCALE = 4  # 4× pixel-perfect
CANVAS_SIZE = 320  # final portrait is 320×320 square with circular tint
# 32x64 sprite * 4 = 128x256 — fits 320 canvas with margin for ring


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected 6-char hex, got {hex_color!r}")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, alpha


def _crop_sprite(sheet_path: Path, crop: dict) -> Image.Image:
    if not sheet_path.exists():
        raise FileNotFoundError(
            f"sprite sheet missing: {sheet_path} — did you copy ./assets/?"
        )
    img = Image.open(sheet_path).convert("RGBA")
    x, y, w, h = crop["x"], crop["y"], crop["w"], crop["h"]
    if x + w > img.width or y + h > img.height:
        raise ValueError(
            f"crop {crop} exceeds sheet size {img.size} for {sheet_path.name}"
        )
    return img.crop((x, y, x + w, y + h))


def _upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize(
        (img.width * factor, img.height * factor),
        resample=Image.Resampling.NEAREST,
    )


def _render_portrait(cfg: dict) -> Image.Image:
    sheet_path = SPRITE_SHEETS_DIR / cfg["sprite_source"]
    sprite = _crop_sprite(sheet_path, cfg["crop"])
    sprite = _upscale(sprite, SCALE)  # 32x48 -> 128x192

    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Circular tinted backdrop (eases the sprite into the card's color theme)
    tint = _hex_to_rgba(cfg["main_color"], alpha=60)
    ring = _hex_to_rgba(cfg["main_color"], alpha=220)
    cx = cy = CANVAS_SIZE // 2
    r = int(CANVAS_SIZE * 0.46)
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=tint, outline=ring, width=6)

    # Paste sprite centered horizontally, slightly above center vertically so
    # head-focus reads cleanly (visual weight of torso pulls the eye down).
    x = (CANVAS_SIZE - sprite.width) // 2
    y = (CANVAS_SIZE - sprite.height) // 2 - 12
    canvas.paste(sprite, (x, y), sprite)
    return canvas


def main() -> int:
    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    bible = load_visual_bible()
    failures: list[str] = []

    for agent_id, cfg in bible.items():
        try:
            img = _render_portrait(cfg)
            out = PORTRAITS_DIR / f"{agent_id}.png"
            img.save(out, format="PNG", optimize=True)
            print(f"  ✓ {agent_id:<16} → {out.relative_to(out.parents[2])}")
        except Exception as exc:
            failures.append(f"{agent_id}: {exc}")
            print(f"  ✗ {agent_id}: {exc}")

    if failures:
        print(f"\n{len(failures)} portrait(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\ngenerated {len(bible)} portraits in {PORTRAITS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
