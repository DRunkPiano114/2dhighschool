#!/usr/bin/env python3
"""One-shot migration: backfill concern ids, last_new_info_day.

Reads every `agents/*/state.json`, inspects each active concern, and:
- assigns a deterministic 6-hex id if missing (blake2b of
  source_day:source_scene:text[:30]:idx). `idx` is the concern's position
  in state.active_concerns, used as a tiebreaker so that two concerns with
  the same (day, "", 30-char prefix) — typical of `compression.py`
  nightly-compress output where `source_scene=""` — do not collide.
- seeds last_new_info_day = max(source_day, last_reinforced_day) so the
  new TTL check in PR3 doesn't evict pre-existing concerns on day 0.
- leaves reinforcement_count at 0 (no historical data to seed from).

Idempotent only for the first run: re-running on a fully migrated state
is a no-op because the script short-circuits when all four new fields
are populated. Safe to re-run after rollback + restore.

Usage:
    uv run python scripts/backfill_concern_ids.py
    uv run python scripts/backfill_concern_ids.py --agents-dir agents
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _stable_id(source_day: int, source_scene: str, text: str, idx: int) -> str:
    """Deterministic 6-hex id. `idx` is the concern's list position;
    prevents same-day same-scene-prefix collisions."""
    key = f"{source_day}:{source_scene}:{text[:30]}:{idx}".encode("utf-8")
    return hashlib.blake2b(key, digest_size=3).hexdigest()


def _backfill_concern(
    concern: dict, idx: int,
) -> tuple[bool, str | None]:
    """Mutate `concern` in place. Returns (changed, assigned_id_or_None)."""
    changed = False
    assigned_id: str | None = None

    if not concern.get("id"):
        new_id = _stable_id(
            int(concern.get("source_day", 0)),
            concern.get("source_scene", "") or "",
            concern.get("text", "") or "",
            idx,
        )
        concern["id"] = new_id
        assigned_id = new_id
        changed = True

    if "id_history" not in concern:
        concern["id_history"] = []
        changed = True

    if "last_new_info_day" not in concern or concern.get("last_new_info_day", 0) == 0:
        seed = max(
            int(concern.get("source_day", 0) or 0),
            int(concern.get("last_reinforced_day", 0) or 0),
        )
        concern["last_new_info_day"] = seed
        changed = True

    if "reinforcement_count" not in concern:
        concern["reinforcement_count"] = 0
        changed = True

    return changed, assigned_id


def backfill_file(path: Path) -> tuple[int, int]:
    """Process one state.json. Returns (concerns_changed, concerns_total)."""
    data = json.loads(path.read_text("utf-8"))
    concerns = data.get("active_concerns") or []
    if not isinstance(concerns, list):
        return (0, 0)

    changed_count = 0
    assigned_ids: list[str] = []
    for idx, concern in enumerate(concerns):
        if not isinstance(concern, dict):
            continue
        changed, assigned = _backfill_concern(concern, idx)
        if changed:
            changed_count += 1
        if assigned is not None:
            assigned_ids.append(assigned)

    # Collision fail-fast: within one file, all assigned ids must be unique.
    # If this fires, the tiebreaker (idx) is not enough — likely malformed
    # input with the same concern repeated.
    if len(assigned_ids) != len(set(assigned_ids)):
        raise RuntimeError(
            f"{path}: duplicate concern ids assigned during backfill "
            f"({assigned_ids}). Investigate input before retrying."
        )

    if changed_count > 0:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8",
        )

    return (changed_count, len(concerns))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agents-dir", default="agents",
        help="directory containing <agent_id>/state.json files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args()

    base = Path(args.agents_dir)
    if not base.exists():
        print(f"ERROR: {base} does not exist", file=sys.stderr)
        return 2

    files = sorted(base.glob("*/state.json"))
    if not files:
        print(f"no state.json under {base}")
        return 0

    total_changed = 0
    total_concerns = 0
    for f in files:
        if args.dry_run:
            # Read-only: load, count changes, but don't write.
            data = json.loads(f.read_text("utf-8"))
            concerns = data.get("active_concerns") or []
            missing = sum(
                1 for c in concerns
                if isinstance(c, dict) and not c.get("id")
            )
            print(f"{f}: {missing}/{len(concerns)} concerns missing id")
            total_changed += missing
            total_concerns += len(concerns)
        else:
            changed, total = backfill_file(f)
            total_changed += changed
            total_concerns += total
            if changed:
                print(f"{f}: backfilled {changed}/{total} concerns")

    print(
        f"\nsummary: touched {total_changed}/{total_concerns} concerns "
        f"across {len(files)} files"
        f"{' (dry-run)' if args.dry_run else ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
