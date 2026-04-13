"""Export simulation data → web/public/data/ for the frontend."""

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
AGENTS = ROOT / "agents"
WORLD = ROOT / "world"
DATA = ROOT / "data"
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
    if not LOGS.exists():
        return []
    result: list[str] = []
    for day_dir in sorted(LOGS.iterdir()):
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
    schedule = _read_json(DATA / "schedule.json")
    progress = _read_json(WORLD / "progress.json")

    agents = {}
    for p in sorted((DATA / "characters").glob("*.json")):
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
    """Merge agent profile + state + self_narrative + relationships → agents/{id}.json."""
    for agent_dir in sorted(AGENTS.iterdir()):
        if not agent_dir.is_dir():
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
        _write_json(OUT / "agents" / f"{aid}.json", merged)
    print(f"  agents/ ({len(list((OUT / 'agents').iterdir()))} agents)")


def export_days(days: list[str]) -> None:
    """Copy scene files + filtered scenes.json + trajectory.json for each day.

    Only scenes with at least one display-worthy group are written to
    scenes.json; original scene files are still copied verbatim so the raw
    archive is preserved, but the dropdown won't surface empty shells.
    """
    if not LOGS.exists():
        print("  No logs/ directory — skipping days export")
        return

    count = 0
    filtered_out = 0
    for day_name in days:
        day_dir = LOGS / day_name
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

        # Copy all scene files (HHMM_*.json but not scenes.json or trajectory.json)
        for f in sorted(day_dir.glob("*.json")):
            if f.name in ("scenes.json", "trajectory.json"):
                continue
            if f.name.startswith("debug"):
                continue
            shutil.copy2(f, out_day / f.name)

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
    if not LOGS.exists():
        print("  No logs/ directory — skipping snapshot backfill")
        return

    snapshot_files = ("state.json", "relationships.json", "self_narrative.json")
    agent_ids = [d.name for d in sorted(AGENTS.iterdir()) if d.is_dir() and (d / "profile.json").exists()]

    # Day 0 initial state (if not exists)
    day0 = LOGS / "day_000" / "agent_snapshots"
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
    for day_dir in sorted(LOGS.iterdir()):
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
    export_events()
    print(f"\nDone → {OUT}")


if __name__ == "__main__":
    main()
