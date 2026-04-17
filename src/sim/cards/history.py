"""Cross-day history loader for the daily report left column.

Loads the current-view persisted snapshot (active concerns + event queue)
for use by `pick_concern_spotlight` / `pick_event_spread` on the *latest*
simulated day only.

Rationale — the per-agent `state.json` and `simulation/world/event_queue.json`
files represent *today's view of the world*, not per-day slices. If the
simulation has advanced to day 9 and the user navigates to day 3, reading
this snapshot on day 3 would fabricate future-dated data: `active_concerns`
entries with `source_day > 3` (negative `days_active`), inflated
`reinforcement_count`, `known_by` lists that include agents who only heard
about the event later. Since per-day snapshotting is a much larger change,
we degrade gracefully: historical views get `None` back and pick functions
fall back to single-day signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..agent.storage import AgentStorage, WorldStorage
from ..config import settings
from ..models.agent import ActiveConcern
from ..models.event import EventQueue
from .assets import PROJECT_ROOT

DAYS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "days"


@dataclass(frozen=True)
class DailyHistory:
    active_concerns_by_agent: dict[str, list[ActiveConcern]]
    event_queue: EventQueue


def _latest_simulated_day(days_dir: Path | None = None) -> int | None:
    """Return the highest-numbered day under `web/public/data/days/`, or None
    if nothing has been exported yet."""
    root = days_dir or DAYS_DIR
    if not root.exists():
        return None
    best: int | None = None
    for p in root.glob("day_*"):
        if not p.is_dir():
            continue
        try:
            n = int(p.name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        if best is None or n > best:
            best = n
    return best


def load_history(up_to_day: int) -> DailyHistory | None:
    """Load cross-day snapshot for a given view-day.

    Returns None for historical views (``up_to_day < latest_simulated_day``)
    because the persisted state is today's-view-of-the-world, not per-day
    slices — using it on a past day would fabricate data (negative
    ``days_active``, inflated ``reinforcement_count``, anachronistic
    "reinforced today" badges).

    Also returns None when there is no persisted state yet (fresh clone /
    pre-first-run), so callers can safely fall back to single-day signals.
    """
    latest = _latest_simulated_day()
    if latest is None or up_to_day < latest:
        return None

    agents_dir = settings.agents_dir
    world_dir = settings.world_dir
    if not agents_dir.exists():
        return None

    concerns: dict[str, list[ActiveConcern]] = {}
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir():
            continue
        state_path = d / "state.json"
        if not state_path.exists():
            continue
        try:
            state = AgentStorage(d.name, agents_dir).load_state()
        except Exception:
            continue
        if state.active_concerns:
            concerns[d.name] = list(state.active_concerns)

    event_queue = EventQueue()
    if (world_dir / "event_queue.json").exists():
        try:
            event_queue = WorldStorage(
                agents_dir=agents_dir, world_dir=world_dir
            ).load_event_queue()
        except Exception:
            event_queue = EventQueue()

    return DailyHistory(
        active_concerns_by_agent=concerns,
        event_queue=event_queue,
    )
