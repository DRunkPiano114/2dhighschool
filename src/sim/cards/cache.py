"""Disk cache for rendered share-card PNGs.

Cache convention: `.cache/cards/{key}.png` under PROJECT_ROOT. Keys are
caller-supplied (e.g. `scene_001_0`, `daily_001`, `agent_fang_yuchen_030`).
Cache invalidation is manual: `rm -rf .cache/cards` after sim rerun. The
infrastructure is deliberately minimal — sim reruns are manual events so
auto-invalidation would add complexity without payoff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from .assets import CACHE_DIR
from .base import save_png


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.png"


def get_or_render(key: str, render_fn: Callable[[], Image.Image]) -> Path:
    """Return the cached PNG path for `key`, rendering + writing it if missing."""
    path = _cache_path(key)
    if path.exists():
        return path
    img = render_fn()
    save_png(img, path)
    return path


def read_bytes(key: str) -> bytes | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    return path.read_bytes()


def clear() -> int:
    """Delete all cached cards. Returns the number of files removed."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for p in CACHE_DIR.glob("*.png"):
        p.unlink()
        count += 1
    return count
