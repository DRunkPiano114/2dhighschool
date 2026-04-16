"""Crop named furniture sprites from LimeZu Modern Interiors / Exteriors sheets.

Each crop becomes a standalone PNG in `canon/tilesets/<category>/<name>.png`,
which the frontend loads as an ordinary sprite texture (same path as character
map sprites). This keeps the renderer simple: no tile indices, no multi-layer
tilemap machinery — each furniture item is a pre-composed sprite you blit at
a tile coordinate.

Re-run this after editing `TILESETS` to regenerate. The crop manifest lives
here as Python rather than JSON because the coordinates are annotated with
tile-grid comments (e.g. `(1,1)–(4,2)`) that help future edits.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from sim.cards.assets import ASSETS_DIR  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
TILESETS_DIR = ROOT / "canon" / "tilesets"

INT = ASSETS_DIR / "moderninteriors-win" / "1_Interiors" / "32x32"
EXT = ASSETS_DIR / "modernexteriors-win" / "Modern_Exteriors_32x32"

# Theme sheet paths
SHEET_CLASSROOM = INT / "Theme_Sorter_32x32" / "5_Classroom_and_library_32x32.png"
SHEET_BEDROOM = INT / "Theme_Sorter_32x32" / "4_Bedroom_32x32.png"
SHEET_KITCHEN = INT / "Theme_Sorter_32x32" / "12_Kitchen_32x32.png"
SHEET_GROCERY = INT / "Theme_Sorter_32x32" / "16_Grocery_store_32x32.png"
SHEET_SCHOOL_EXT = EXT / "ME_Theme_Sorter_32x32" / "13_School_32x32.png"


# Crop manifest. Keys are tile coordinates (col, row, w_tiles, h_tiles); the
# extractor converts to pixel rects. One entry per output PNG.
#
#   category → { name: (sheet, col, row, w_tiles, h_tiles) }
#
# w_tiles/h_tiles are in TILE units (32px each). Names should be lowercase
# snake_case so they map 1:1 to sprite filenames.
TILESETS: dict[str, dict[str, tuple[Path, int, int, int, int]]] = {
    "classroom": {
        # Teacher podium with writing materials on top (4 wide × 2 tall)
        "teacher_desk": (SHEET_CLASSROOM, 1, 1, 4, 2),
        # Teacher desk w/ open book + bottle (2×2)
        "teacher_desk_book": (SHEET_CLASSROOM, 5, 1, 2, 2),
        # Single top-down student desk (1×2). Previously labelled _alt — the
        # (3,3) neighbour turned out to be a side-view chair fragment.
        "student_desk": (SHEET_CLASSROOM, 5, 3, 1, 2),
        # Green chair (front-view, 1×2)
        "chair_green": (SHEET_CLASSROOM, 0, 1, 1, 2),
        # Big flat blackboard with chalk tray (2×2)
        "chalkboard_black": (SHEET_CLASSROOM, 13, 5, 2, 2),
        # Educational poster with green book + ABC chart (2×2)
        "poster_abc": (SHEET_CLASSROOM, 8, 0, 2, 2),
        # Colourful number/letter grid poster (2×2)
        "poster_numbers": (SHEET_CLASSROOM, 13, 3, 2, 2),
        # Cork notice board (2×1)
        "notice_board": (SHEET_CLASSROOM, 0, 6, 2, 1),
    },
    "library": {
        "bookshelf_tall_a": (SHEET_CLASSROOM, 0, 12, 2, 3),
        "bookshelf_tall_b": (SHEET_CLASSROOM, 2, 12, 2, 3),
        "bookshelf_tall_c": (SHEET_CLASSROOM, 4, 12, 2, 3),
        "bookshelf_short": (SHEET_CLASSROOM, 0, 7, 2, 2),
        "bookshelf_colorful": (SHEET_CLASSROOM, 7, 7, 2, 2),
        "reading_table": (SHEET_CLASSROOM, 7, 3, 2, 2),
    },
    "dorm": {
        "bed_green": (SHEET_BEDROOM, 8, 20, 2, 4),
        "bed_blue": (SHEET_BEDROOM, 10, 20, 2, 4),
        "bed_pink": (SHEET_BEDROOM, 12, 20, 2, 4),
        "wardrobe": (SHEET_BEDROOM, 12, 0, 2, 3),
    },
    "cafeteria": {
        "fridge": (SHEET_KITCHEN, 8, 24, 2, 4),
        "stove": (SHEET_KITCHEN, 8, 11, 2, 2),
        "counter_long": (SHEET_KITCHEN, 0, 11, 4, 2),
        "dining_table": (SHEET_KITCHEN, 4, 28, 2, 4),
    },
    "store": {
        "vending_a": (SHEET_GROCERY, 0, 16, 2, 2),
        "vending_b": (SHEET_GROCERY, 2, 16, 2, 2),
        "shelf_tall": (SHEET_GROCERY, 0, 2, 2, 4),
        "cooler_glass": (SHEET_GROCERY, 12, 4, 2, 4),
        "register": (SHEET_GROCERY, 6, 20, 2, 2),
    },
    "sports": {
        # Full horizontal court — 13×10 tiles at (4,47). Landscape orientation
        # fits the playground room (30×20) much better than the vertical 8×12.
        "basketball_court": (SHEET_SCHOOL_EXT, 4, 47, 13, 10),
    },
}


def _crop(sheet_path: Path, col: int, row: int, w_tiles: int, h_tiles: int) -> Image.Image:
    if not sheet_path.exists():
        raise FileNotFoundError(f"sheet missing: {sheet_path} — did you copy ./assets/?")
    img = Image.open(sheet_path).convert("RGBA")
    x, y = col * 32, row * 32
    w, h = w_tiles * 32, h_tiles * 32
    if x + w > img.width or y + h > img.height:
        raise ValueError(
            f"crop ({col},{row},{w_tiles}×{h_tiles}) exceeds {sheet_path.name} "
            f"{img.size} — max ({img.width//32},{img.height//32})"
        )
    return img.crop((x, y, x + w, y + h))


def _strip_vegetation(img: Image.Image) -> Image.Image:
    """Remove green vegetation pixels from outdoor sprites (e.g. basketball court).

    Vegetation on the school exterior sheet has distinctly green hues that
    bleed into the crop. Replace them with full transparency so the room's
    grass floor shows through cleanly without stray bush artifacts.
    """
    import numpy as np

    arr = np.array(img, dtype=np.uint8)  # (H, W, 4) RGBA
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    # Step 1: remove green-dominant pixels (vegetation hue, incl. teal)
    green_mask = (
        (g > 60)
        & (g.astype(int) > r.astype(int) + 10)
        & (g.astype(int) > b.astype(int))
        & (a > 0)
    )
    arr[green_mask, 3] = 0
    # Step 2: remove small isolated pixel clusters left behind (trunk
    # outlines, highlights) that are no longer connected to the main body.
    from scipy import ndimage

    visible = arr[..., 3] > 0
    labels, n = ndimage.label(visible)
    # Keep only the largest connected component (the court itself)
    if n > 1:
        sizes = ndimage.sum(visible, labels, range(1, n + 1))
        keep_label = int(np.argmax(sizes)) + 1
        arr[labels != keep_label, 3] = 0
    return Image.fromarray(arr, "RGBA")


def main() -> int:
    TILESETS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, dict[str, int]]] = {}
    failures: list[str] = []
    count = 0

    for category, items in TILESETS.items():
        cat_dir = TILESETS_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        manifest[category] = {}
        for name, (sheet, col, row, w, h) in items.items():
            try:
                img = _crop(sheet, col, row, w, h)
                if name == "basketball_court":
                    img = _strip_vegetation(img)
                out = cat_dir / f"{name}.png"
                img.save(out, format="PNG", optimize=True)
                manifest[category][name] = {"w": w * 32, "h": h * 32, "tiles_w": w, "tiles_h": h}
                print(f"  ✓ {category}/{name:<22} {w}×{h} tiles")
                count += 1
            except Exception as exc:
                failures.append(f"{category}/{name}: {exc}")
                print(f"  ✗ {category}/{name}: {exc}")

    # Emit manifest so frontend knows sprite dimensions without loading each PNG
    import json

    manifest_path = TILESETS_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  manifest.json ({count} sprites)")

    if failures:
        print(f"\n{len(failures)} crop(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\ngenerated {count} tileset sprites in {TILESETS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
