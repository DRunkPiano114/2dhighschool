"""Paper-texture background (procedural) — re-exports from base.py.

Kept as a separate module so future richer backgrounds (Papernote theme asset
overlays) can be swapped in without touching base.py.
"""

from __future__ import annotations

from ..base import paper_background

__all__ = ["paper_background"]
