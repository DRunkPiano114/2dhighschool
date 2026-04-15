"""Resource paths and visual-bible loader for share cards."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = PROJECT_ROOT / "fonts"
DATA_DIR = PROJECT_ROOT / "data"
PORTRAITS_DIR = DATA_DIR / "portraits"
VISUAL_BIBLE_PATH = DATA_DIR / "visual_bible.json"
CACHE_DIR = PROJECT_ROOT / ".cache" / "cards"

SPRITE_SHEETS_DIR = (
    ASSETS_DIR
    / "moderninteriors-win"
    / "2_Characters"
    / "Character_Generator"
    / "0_Premade_Characters"
    / "32x32"
)

FONT_LXGW_REGULAR = FONTS_DIR / "LXGWWenKai-Regular.ttf"
FONT_SERIF_REGULAR = FONTS_DIR / "NotoSerifSC-Regular.ttf"
FONT_SERIF_BOLD = FONTS_DIR / "NotoSerifSC-Bold.ttf"
FONT_SANS_REGULAR = FONTS_DIR / "NotoSansSC-Regular.ttf"
FONT_SANS_BOLD = FONTS_DIR / "NotoSansSC-Bold.ttf"


@lru_cache(maxsize=1)
def load_visual_bible() -> dict[str, dict[str, Any]]:
    """Load the visual-bible mapping (agent_id → visual config).

    Keys starting with '_' (e.g. '_comment') are filtered out.
    """
    raw = json.loads(VISUAL_BIBLE_PATH.read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def get_agent_visual(agent_id: str) -> dict[str, Any]:
    bible = load_visual_bible()
    if agent_id not in bible:
        raise KeyError(f"agent_id '{agent_id}' not in visual_bible.json")
    return bible[agent_id]


def portrait_path(agent_id: str) -> Path:
    return PORTRAITS_DIR / f"{agent_id}.png"
