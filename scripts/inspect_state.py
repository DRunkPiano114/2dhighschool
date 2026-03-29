"""Debug tool: inspect current simulation state."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sim.agent.storage import WorldStorage


def inspect_agent(agent_id: str | None = None) -> None:
    ws = WorldStorage()
    ws.load_all_agents()

    if agent_id:
        agents = {agent_id: ws.agents[agent_id]} if agent_id in ws.agents else {}
    else:
        agents = ws.agents

    if not agents:
        print("No agents found (or agent_id not found).")
        return

    for aid, storage in agents.items():
        profile = storage.load_profile()
        state = storage.load_state()
        rels = storage.load_relationships()
        km = storage.load_key_memories()
        today = storage.read_today_md()
        recent = storage.read_recent_md()

        print(f"\n{'='*60}")
        print(f"  {profile.name} ({aid})")
        print(f"{'='*60}")
        print(f"  Role: {profile.role.value} | Gender: {profile.gender.value}")
        print(f"  Personality: {', '.join(profile.personality)}")
        print(f"  Seat: {profile.seat_number} | Dorm: {profile.dorm_id}")
        print(f"  Rank: {profile.academics.overall_rank.value} | Target: {profile.academics.target.value}")
        print()
        print(f"  --- State ---")
        print(f"  Emotion: {state.emotion.value} | Energy: {state.energy} | Pressure: {state.academic_pressure}")
        print(f"  Day: {state.day} | Location: {state.location}")
        if state.daily_plan.intentions:
            print(f"  Intentions:")
            for i in state.daily_plan.intentions:
                status = "DONE" if i.fulfilled else "pending"
                print(f"    [{status}] {i.goal} (target={i.target})")
        print()
        print(f"  --- Relationships ({len(rels.relationships)}) ---")
        for tid, rel in sorted(rels.relationships.items(), key=lambda x: -x[1].favorability):
            print(f"    {rel.target_name} ({rel.label}): fav={rel.favorability} trust={rel.trust} und={rel.understanding}")
            if rel.recent_interactions:
                for ri in rel.recent_interactions[-3:]:
                    print(f"      - {ri}")
        print()
        print(f"  --- Key Memories ({len(km.memories)}) ---")
        for m in km.memories[-5:]:
            print(f"    [Day {m.day}, imp={m.importance}] {m.text[:80]}")
        print()
        if today.strip():
            print(f"  --- Today ---")
            print(f"  {today[:300]}")
            print()
        if recent.strip():
            print(f"  --- Recent (last 200 chars) ---")
            print(f"  {recent[-200:]}")
            print()


def inspect_world() -> None:
    ws = WorldStorage()
    progress = ws.load_progress()
    eq = ws.load_event_queue()

    print(f"\n{'='*60}")
    print(f"  WORLD STATE")
    print(f"{'='*60}")
    print(f"  Day: {progress.current_day} | Phase: {progress.day_phase}")
    print(f"  Total simulated: {progress.total_days_simulated} days")
    print(f"  Next exam in: {progress.next_exam_in_days} days")
    print(f"  Last updated: {progress.last_updated}")
    print()
    print(f"  --- Events ({len(eq.events)} total, {sum(1 for e in eq.events if e.active)} active) ---")
    for e in eq.events:
        status = "ACTIVE" if e.active else "expired"
        print(f"    [{status}] {e.text} (known by: {', '.join(e.known_by)})")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect simulation state")
    parser.add_argument("--agent", type=str, default=None, help="Agent ID to inspect (default: all)")
    parser.add_argument("--world", action="store_true", help="Show world state")
    parser.add_argument("--all", action="store_true", help="Show everything")
    args = parser.parse_args()

    if args.all or (not args.agent and not args.world):
        inspect_world()
        inspect_agent()
    elif args.world:
        inspect_world()
    elif args.agent:
        inspect_agent(args.agent)


if __name__ == "__main__":
    main()
