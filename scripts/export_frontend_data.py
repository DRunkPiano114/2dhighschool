"""Export simulation data → web/public/data/ for the frontend."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
AGENTS = ROOT / "agents"
WORLD = ROOT / "world"
DATA = ROOT / "data"
OUT = ROOT / "web" / "public" / "data"


def _read_json(p: Path) -> dict | list:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def export_meta() -> None:
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

    days = sorted(d.name for d in LOGS.iterdir() if d.is_dir() and d.name.startswith("day_")) if LOGS.exists() else []

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


def export_days() -> None:
    """Copy scene files, scenes.json, trajectory.json for each day."""
    if not LOGS.exists():
        print("  No logs/ directory — skipping days export")
        return

    count = 0
    for day_dir in sorted(LOGS.iterdir()):
        if not day_dir.is_dir() or not day_dir.name.startswith("day_"):
            continue
        out_day = OUT / "days" / day_dir.name
        out_day.mkdir(parents=True, exist_ok=True)

        # Copy scenes.json
        scenes_path = day_dir / "scenes.json"
        if scenes_path.exists():
            shutil.copy2(scenes_path, out_day / "scenes.json")

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
    print(f"  days/ ({count} days)")


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


def main() -> None:
    # Clean output
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    print("Exporting frontend data...")
    export_meta()
    export_agents()
    export_days()
    export_events()
    print(f"\nDone → {OUT}")


if __name__ == "__main__":
    main()
