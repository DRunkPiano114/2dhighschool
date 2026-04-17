"""Export simulation data → web/public/data/ for the frontend."""

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DAYS = ROOT / "simulation" / "days"
AGENTS = ROOT / "simulation" / "state"
WORLD = ROOT / "simulation" / "world"
CAST = ROOT / "canon" / "cast"
WORLDBOOK = ROOT / "canon" / "worldbook"
OUT = ROOT / "web" / "public" / "data"


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_group_display_worthy(group: dict) -> bool:
    """A group is worth showing in the UI if it has real content.

    Multi-agent: at least one tick (backend marks trivial scenes as ticks=[]).
    Solo: solo_reflection exists with non-empty inner_thought or activity.
    """
    if group.get("is_solo"):
        sr = group.get("solo_reflection") or {}
        return bool((sr.get("inner_thought") or "").strip() or (sr.get("activity") or "").strip())
    return len(group.get("ticks") or []) > 0


def _is_scene_display_worthy(scene_file: dict) -> bool:
    return any(_is_group_display_worthy(g) for g in scene_file.get("groups", []))


def _display_worthy_days() -> list[str]:
    """Days whose scenes.json has at least one display-worthy scene."""
    if not DAYS.exists():
        return []
    result: list[str] = []
    for day_dir in sorted(DAYS.iterdir()):
        if not (day_dir.is_dir() and day_dir.name.startswith("day_")):
            continue
        scenes_path = day_dir / "scenes.json"
        if not scenes_path.exists():
            continue
        scenes = _read_json(scenes_path)
        has_content = False
        for scene in scenes:
            file_path = day_dir / scene.get("file", "")
            if not file_path.exists():
                continue
            scene_file = _read_json(file_path)
            if _is_scene_display_worthy(scene_file):
                has_content = True
                break
        if has_content:
            result.append(day_dir.name)
    return result


def export_meta(days: list[str]) -> None:
    """Build meta.json with days list, agent IDs/names, schedule."""
    schedule = _read_json(WORLDBOOK / "schedule.json")
    progress = _read_json(WORLD / "progress.json")

    agents = {}
    for p in sorted((CAST / "profiles").glob("*.json")):
        c = _read_json(p)
        agents[c["agent_id"]] = {
            "name": c["name"],
            "role": c["role"],
            "gender": c.get("gender"),
            "seat_number": c.get("seat_number"),
            "position": c.get("position"),
            "dorm_id": c.get("dorm_id"),
        }

    meta = {
        "days": days,
        "agents": agents,
        "schedule": schedule,
        "current_date": progress.get("current_date", "2025-09-01"),
        "next_exam_in_days": progress.get("next_exam_in_days", 30),
    }
    _write_json(OUT / "meta.json", meta)
    print(f"  meta.json ({len(days)} days, {len(agents)} agents)")


def export_agents() -> None:
    """Merge agent profile + state + self_narrative + relationships → agents/{id}/profile.json."""
    for agent_dir in sorted(AGENTS.iterdir()):
        if not agent_dir.is_dir() or not (agent_dir / "profile.json").exists():
            continue
        aid = agent_dir.name
        profile = _read_json(agent_dir / "profile.json")
        state = _read_json(agent_dir / "state.json")
        relationships = _read_json(agent_dir / "relationships.json")

        self_narrative_path = agent_dir / "self_narrative.md"
        self_narrative = self_narrative_path.read_text(encoding="utf-8").strip() if self_narrative_path.exists() else ""

        key_memories = []
        km_path = agent_dir / "key_memories.json"
        if km_path.exists():
            key_memories = _read_json(km_path)

        merged = {
            **profile,
            "state": state,
            "relationships": relationships.get("relationships", {}),
            "self_narrative": self_narrative,
            "key_memories": key_memories,
        }
        _write_json(OUT / "agents" / aid / "profile.json", merged)
    print(f"  agents/ ({len(list((OUT / 'agents').iterdir()))} agents)")


def export_daily_summaries(days: list[str]) -> None:
    """Serialize build_daily_summary() for each day → daily/{day:03d}.json."""
    from sim.cards.aggregations import build_daily_summary, summary_to_dict
    from sim.cards.captions import daily_caption

    count = 0
    for day_name in days:
        day = int(day_name.removeprefix("day_"))
        try:
            summary = build_daily_summary(day)
        except FileNotFoundError:
            continue
        summary_dict = summary_to_dict(summary)
        headline = summary.headline
        cp = summary.cp
        summary_dict["caption_payload"] = daily_caption(
            day=day,
            headline_quote=headline.thought if headline else None,
            headline_speaker=(headline.thought_name or headline.speaker_name) if headline else None,
            cp_pair=(cp.a_name, cp.b_name) if cp else None,
        )
        _write_json(OUT / "daily" / f"{day:03d}.json", summary_dict)
        count += 1
    print(f"  daily/ ({count} summaries)")


def export_agent_day_specs(days: list[str]) -> None:
    """Serialize build_agent_spec() for each (agent, day) → agents/{id}/days/{day:03d}.json."""
    from sim.agent.storage import WorldStorage
    from sim.cards.agent_card import build_agent_spec, spec_to_dict
    from sim.cards.captions import agent_caption

    world = WorldStorage()
    world.load_all_agents()

    count = 0
    for day_name in days:
        day = int(day_name.removeprefix("day_"))
        for aid in world.agents:
            try:
                spec = build_agent_spec(aid, day, world)
            except (KeyError, FileNotFoundError):
                continue
            spec_dict = spec_to_dict(spec)
            spec_dict["caption_payload"] = agent_caption(
                day=day,
                agent_name_cn=spec.name_cn,
                motif_emoji=spec.motif_emoji,
                motif_tag=spec.motif_tag,
                emotion_label=spec.emotion_label,
                featured_quote=spec.featured_quote,
            )
            _write_json(OUT / "agents" / aid / "days" / f"{day:03d}.json", spec_dict)
            count += 1
    print(f"  agents/*/days/ ({count} day specs)")


def _inject_scene_share_data(scene_file: dict) -> dict:
    """For each multi-agent group with ticks, inject per-tick share_tick_layouts
    and share_tick_captions arrays (one entry per tick, aligned with
    group['ticks']). The frontend picks the entry matching the user's current
    tick at save time, so 保存图 matches the bubble the user was reading.
    Python still owns all selection/ordering logic — the React component is
    just a pure renderer.
    """
    from sim.cards.assets import load_visual_bible
    from sim.cards.captions import scene_caption
    from sim.cards.scene_card import scene_to_layout_spec, spec_to_dict

    bible = load_visual_bible()
    for gi, group in enumerate(scene_file.get("groups", [])):
        if group.get("is_solo") or len(group.get("participants", [])) < 2:
            continue
        ticks = group.get("ticks") or []
        if not ticks:
            continue
        tick_layouts: list[dict] = []
        tick_captions: list[dict] = []
        for ti in range(len(ticks)):
            try:
                spec = scene_to_layout_spec(scene_file, gi, tick_index=ti)
            except Exception:
                # Placeholder so array indices stay aligned with group['ticks'].
                tick_layouts.append({})
                tick_captions.append({})
                continue
            motif_emoji = ""
            if spec.bubbles:
                motif_emoji = bible.get(spec.bubbles[0].agent_id, {}).get("motif_emoji", "")
            caption = scene_caption(
                day=spec.day,
                scene_name=spec.scene_name,
                location=spec.location,
                time=spec.time,
                featured_quote=spec.featured_quote,
                featured_speaker=spec.featured_speaker_name,
                motif_emoji=motif_emoji,
                tick_index=ti,
            )
            caption["group_index"] = gi
            caption["tick_index"] = ti
            tick_layouts.append(spec_to_dict(spec))
            tick_captions.append(caption)
        group["share_tick_layouts"] = tick_layouts
        group["share_tick_captions"] = tick_captions
    return scene_file


def export_days(days: list[str]) -> None:
    """Copy scene files + filtered scenes.json + trajectory.json for each day.

    Only scenes with at least one display-worthy group are written to
    scenes.json; original scene files are still copied verbatim so the raw
    archive is preserved, but the dropdown won't surface empty shells.
    """
    if not DAYS.exists():
        print("  No simulation/days/ directory — skipping days export")
        return

    count = 0
    filtered_out = 0
    for day_name in days:
        day_dir = DAYS / day_name
        if not day_dir.is_dir():
            continue
        out_day = OUT / "days" / day_name
        out_day.mkdir(parents=True, exist_ok=True)

        # Filter scenes.json by display-worthiness
        scenes_path = day_dir / "scenes.json"
        if scenes_path.exists():
            scenes = _read_json(scenes_path)
            kept = []
            for scene in scenes:
                file_path = day_dir / scene.get("file", "")
                if not file_path.exists():
                    continue
                if _is_scene_display_worthy(_read_json(file_path)):
                    kept.append(scene)
                else:
                    filtered_out += 1
            _write_json(out_day / "scenes.json", kept)

        # Copy trajectory.json
        traj_path = day_dir / "trajectory.json"
        if traj_path.exists():
            shutil.copy2(traj_path, out_day / "trajectory.json")

        # Copy scene files with share_caption_payload + share_layout injected
        # on each multi-agent group. The frontend <SceneShareCard> consumes
        # these directly — Python owns the selection/ordering logic.
        for f in sorted(day_dir.glob("*.json")):
            if f.name in ("scenes.json", "trajectory.json"):
                continue
            if f.name.startswith("debug"):
                continue
            _write_json(out_day / f.name, _inject_scene_share_data(_read_json(f)))

        count += 1
    print(f"  days/ ({count} days, {filtered_out} empty scenes filtered from dropdowns)")


def export_events() -> None:
    """Copy event_queue.json → events.json."""
    eq_path = WORLD / "event_queue.json"
    if eq_path.exists():
        eq = _read_json(eq_path)
        _write_json(OUT / "events.json", eq.get("events", []))
        print(f"  events.json ({len(eq.get('events', []))} events)")
    else:
        _write_json(OUT / "events.json", [])
        print("  events.json (empty)")


def backfill_snapshots() -> None:
    """Create agent_snapshots for already-simulated days that lack them.

    For each day_NNN directory, if agent_snapshots/ is missing, copy current
    agent files as the snapshot. This is a one-time migration: future runs
    create snapshots automatically via the orchestrator.
    """
    if not DAYS.exists():
        print("  No simulation/days/ directory — skipping snapshot backfill")
        return

    snapshot_files = ("state.json", "relationships.json", "self_narrative.json")
    agent_ids = [d.name for d in sorted(AGENTS.iterdir()) if d.is_dir() and (d / "profile.json").exists()]

    # Day 0 initial state (if not exists)
    day0 = DAYS / "day_000" / "agent_snapshots"
    if not day0.exists():
        for aid in agent_ids:
            dest = day0 / aid
            dest.mkdir(parents=True, exist_ok=True)
            for fname in snapshot_files:
                src = AGENTS / aid / fname
                if src.exists():
                    shutil.copy2(src, dest / fname)
        print(f"  Created Day 0 snapshot ({len(agent_ids)} agents)")

    # Backfill any day_NNN dirs missing agent_snapshots
    count = 0
    for day_dir in sorted(DAYS.iterdir()):
        if not day_dir.is_dir() or not day_dir.name.startswith("day_"):
            continue
        if day_dir.name == "day_000":
            continue
        snap_dir = day_dir / "agent_snapshots"
        if snap_dir.exists():
            continue
        # Use current agent files as best-available snapshot
        for aid in agent_ids:
            dest = snap_dir / aid
            dest.mkdir(parents=True, exist_ok=True)
            for fname in snapshot_files:
                src = AGENTS / aid / fname
                if src.exists():
                    shutil.copy2(src, dest / fname)
        count += 1
    if count:
        print(f"  Backfilled snapshots for {count} days")


def export_portraits() -> None:
    """Copy agent portraits into web/public/data/portraits/ for the gallery."""
    src = CAST / "portraits"
    dst = OUT / "portraits"
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        print("  No canon/cast/portraits/ — skipping portrait export")
        return
    shutil.copytree(src, dst)
    n = len(list(dst.glob("*.png")))
    print(f"  portraits/ ({n} files)")


def export_map_sprites() -> None:
    """Copy transparent-bg pixel sprites used on the world map."""
    src = CAST / "map_sprites"
    dst = OUT / "map_sprites"
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        print("  No canon/cast/map_sprites/ — skipping map sprite export")
        return
    shutil.copytree(src, dst)
    n = len(list(dst.glob("*.png")))
    print(f"  map_sprites/ ({n} files)")


def export_tilesets() -> None:
    """Copy room furniture sprites (+ manifest.json) used to paint the map.

    Generated upstream by `scripts/generate_tilesets.py` from LimeZu sheets.
    """
    src = ROOT / "canon" / "tilesets"
    dst = OUT / "tilesets"
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        print("  No canon/tilesets/ — run generate_tilesets.py first")
        return
    shutil.copytree(src, dst)
    n = sum(1 for _ in dst.rglob("*.png"))
    print(f"  tilesets/ ({n} sprites + manifest.json)")


def export_balloons() -> None:
    """Copy emotion→balloon PNGs generated by scripts/generate_balloons.py."""
    src = ROOT / "canon" / "balloons"
    dst = OUT / "balloons"
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        print("  No canon/balloons/ — run generate_balloons.py first")
        return
    shutil.copytree(src, dst)
    n = len(list(dst.glob("*.png")))
    print(f"  balloons/ ({n} files)")


def export_animated() -> None:
    """Copy animated-object sprite sheets + manifest generated by
    scripts/generate_animated.py.
    """
    src = ROOT / "canon" / "animated"
    dst = OUT / "animated"
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        print("  No canon/animated/ — run generate_animated.py first")
        return
    shutil.copytree(src, dst)
    n = sum(1 for _ in dst.rglob("*.png"))
    print(f"  animated/ ({n} sheets + manifest.json)")


def export_agent_colors() -> None:
    """Emit agent_colors.json so the frontend has a single source of truth for
    per-agent palette. Kills the sync hazard between visual_bible.json and
    CharacterSprite.ts's hardcoded AGENT_COLORS table.
    """
    bible = _read_json(CAST / "visual_bible.json")
    colors = {
        aid: {
            "main_color": cfg["main_color"],
            "accent_color": cfg.get("accent_color"),
            "motif_emoji": cfg.get("motif_emoji"),
        }
        for aid, cfg in bible.items()
        if not aid.startswith("_")
    }
    _write_json(OUT / "agent_colors.json", colors)
    print(f"  agent_colors.json ({len(colors)} agents)")


def main() -> None:
    # Clean output
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    print("Exporting frontend data...")
    backfill_snapshots()
    # Compute day list once — only days with at least one display-worthy scene.
    # This drops the day_000 init placeholder and any future empty days.
    days = _display_worthy_days()
    export_meta(days)
    export_agents()
    export_days(days)
    # export_daily_summaries / export_agent_day_specs depend on
    # web/public/data/days/ being populated (build_daily_summary /
    # build_context_at_timepoint read from there via aggregations.py and
    # api/context.py).
    export_daily_summaries(days)
    export_agent_day_specs(days)
    export_events()
    export_portraits()
    export_map_sprites()
    export_tilesets()
    export_animated()
    export_balloons()
    export_agent_colors()
    print(f"\nDone → {OUT}")


if __name__ == "__main__":
    main()
