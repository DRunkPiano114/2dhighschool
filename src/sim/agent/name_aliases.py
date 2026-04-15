"""Name alias normalization.

Maps informal appellations ("爸爸") to canonical form ("父亲") for
comparison only. Rendered text (prompts, narrative) keeps the original
form the LLM wrote — only strings entering set operations or equality
checks get normalized.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import settings


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, str]:
    path: Path = settings.worldbook_dir / "name_aliases.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text("utf-8"))
    # Prefer the nested `aliases` block (current schema). Fall back to a
    # flat dict for back-compat; strip metadata-only keys prefixed with `_`.
    if isinstance(raw, dict) and "aliases" in raw:
        inner = raw["aliases"]
        if not isinstance(inner, dict):
            return {}
        return {str(k): str(v) for k, v in inner.items()}
    if isinstance(raw, dict):
        return {
            str(k): str(v) for k, v in raw.items()
            if not str(k).startswith("_")
        }
    return {}


def normalize(name: str) -> str:
    """Return the canonical name for comparison; falls through unchanged
    when no alias is registered."""
    if not name:
        return name
    return _load_aliases().get(name, name)


def reset_cache() -> None:
    """Test hook — drop the memoized table so a rewritten JSON file
    on disk is picked up in-process."""
    _load_aliases.cache_clear()
