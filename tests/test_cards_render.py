"""Render smoke tests — no pixel/byte comparisons.

Pillow output is not byte-deterministic across libfreetype + font-hinting
versions, so we verify only that the render pipeline *runs*, produces a PNG,
and honors canvas size. Visual correctness is validated by the Phase 0
self_test → prototype_scene_card.png sign-off path, not by CI.
"""

from __future__ import annotations

import io

import pytest

from sim.cards import scene_card
from sim.cards.base import CANVAS_H, CANVAS_W


@pytest.fixture
def sample_scene() -> dict:
    """Day 1 scene 0 (早读) — a real exported scene file."""
    return scene_card.load_scene_by_array_index(1, 0)


def test_render_returns_pil_image(sample_scene):
    group_idx = scene_card.select_featured_group(sample_scene)
    assert group_idx is not None
    spec = scene_card.scene_to_layout_spec(sample_scene, group_idx)
    img = scene_card._render_card(spec)
    assert img.size == (CANVAS_W, CANVAS_H)
    assert img.mode == "RGBA"


def test_render_encodes_to_valid_png(sample_scene):
    group_idx = scene_card.select_featured_group(sample_scene)
    assert group_idx is not None
    spec = scene_card.scene_to_layout_spec(sample_scene, group_idx)
    img = scene_card._render_card(spec)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    # PNG magic bytes
    assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_full_path_returns_none_for_solo_only_scene(tmp_path, monkeypatch):
    """If every group is solo, render() returns None (API → 404)."""
    fake = {
        "scene": {"day": 1, "time": "07:00", "name": "x", "location": "教室", "description": ""},
        "participant_names": {"a": "甲"},
        "groups": [{"group_index": 0, "participants": ["a"], "is_solo": True}],
    }
    # Monkey-patch the loader so render() picks up our fake.
    monkeypatch.setattr(scene_card, "load_scene_by_array_index", lambda d, i: fake)
    assert scene_card.render(1, 0) is None


def test_scene_loader_raises_for_missing_day():
    with pytest.raises(FileNotFoundError):
        scene_card.load_scenes_index(999)


def test_scene_loader_raises_for_out_of_range_idx():
    with pytest.raises(IndexError):
        scene_card.load_scene_by_array_index(1, 999)


def test_render_day_1_scene_0_end_to_end():
    """Smoke: a real exported scene renders without raising."""
    img = scene_card.render(1, 0)
    assert img is not None
    assert img.size == (CANVAS_W, CANVAS_H)
