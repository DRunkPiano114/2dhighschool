"""Generate per-agent pixel-art map sprites from LimeZu premade sprite sheets.

Unlike generate_portraits.py (which composites onto a circular tinted canvas
for UI cards), this script emits the raw 32x64 sprite on a transparent
background. These are the sprites rendered on the world map — they need to
sit on top of tile art without a framed badge around them.

Idempotent: produces byte-identical output on re-runs. Reads
`canon/cast/visual_bible.json` and writes `canon/cast/map_sprites/{agent_id}.png`
per agent.

Re-run after changing `sprite_source` or `crop` in visual_bible.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from sim.cards.assets import (
    CAST_DIR,
    SPRITE_SHEETS_DIR,
    load_visual_bible,
)

MAP_SPRITES_DIR = CAST_DIR / "map_sprites"


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


def main() -> int:
    MAP_SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    bible = load_visual_bible()
    failures: list[str] = []

    for agent_id, cfg in bible.items():
        try:
            sheet_path = SPRITE_SHEETS_DIR / cfg["sprite_source"]
            sprite = _crop_sprite(sheet_path, cfg["crop"])
            out = MAP_SPRITES_DIR / f"{agent_id}.png"
            sprite.save(out, format="PNG", optimize=True)
            print(f"  ✓ {agent_id:<16} → {out.relative_to(out.parents[2])}")
        except Exception as exc:
            failures.append(f"{agent_id}: {exc}")
            print(f"  ✗ {agent_id}: {exc}")

    if failures:
        print(f"\n{len(failures)} sprite(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\ngenerated {len(bible)} map sprites in {MAP_SPRITES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
