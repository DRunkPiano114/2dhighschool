"""Resource paths and visual-bible loader shared by card projection + asset-gen scripts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = PROJECT_ROOT / "assets"
CAST_DIR = PROJECT_ROOT / "canon" / "cast"
PORTRAITS_DIR = CAST_DIR / "portraits"
VISUAL_BIBLE_PATH = CAST_DIR / "visual_bible.json"

SPRITE_SHEETS_DIR = (
    ASSETS_DIR
    / "moderninteriors-win"
    / "2_Characters"
    / "Character_Generator"
    / "0_Premade_Characters"
    / "32x32"
)


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
