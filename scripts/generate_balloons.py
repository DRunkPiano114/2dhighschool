"""Crop first-frame 32×32 pixel-art chat balloons from the wento balloon pack.

Maps each Emotion to a balloon name, pulls the first frame, saves to
`canon/balloons/<emotion>.png`. BubbleOverlay loads these to replace the
Unicode emoji bubbles.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from sim.cards.assets import ASSETS_DIR  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "canon" / "balloons"
SRC = ASSETS_DIR / "32x32_emote-chat-balloons_pack" / "png-animated-expressions-separatedly"

# Emotion → balloon file basename (without the 32x32_balloon- prefix).
# Kept in sync with web/src/lib/constants.ts EMOTION_EMOJIS.
MAP: dict[str, str] = {
    "happy": "laugh",
    "sad": "cry",
    "anxious": "exclamation",
    "angry": "angry",
    "excited": "star",
    "calm": "dots",
    "embarrassed": "blush",
    "bored": "yawn",
    "neutral": "dots",
    "jealous": "evil",
    "proud": "star",
    "guilty": "cry",
    "frustrated": "dizzy",
    "touched": "heart",
    "curious": "question",
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in OUT_DIR.glob("*.png"):
        p.unlink()

    n = 0
    for emotion, bname in MAP.items():
        src = SRC / f"32x32_balloon-{bname}.png"
        if not src.exists():
            print(f"  ✗ {emotion}: missing {src.name}")
            continue
        img = Image.open(src).convert("RGBA")
        # Each sheet is a horizontal frame strip. First 32×32 = frame 0.
        frame = img.crop((0, 0, 32, 32))
        out = OUT_DIR / f"{emotion}.png"
        frame.save(out, format="PNG", optimize=True)
        print(f"  ✓ {emotion:<14} ← {bname}")
        n += 1
    print(f"\ngenerated {n} balloon sprites in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
