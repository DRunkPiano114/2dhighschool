import asyncio
import sys

from loguru import logger

from .agent.storage import WorldStorage
from .interaction.orchestrator import Orchestrator


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run high school class simulation")
    parser.add_argument("--days", type=int, default=1, help="Number of days to simulate")
    parser.add_argument("--start-day", type=int, default=None, help="Start day (default: resume from progress)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--log-level", default="INFO", help="Log level (DEBUG/INFO/WARNING)")
    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level=args.log_level)
    logger.add("logs/sim.log", rotation="10 MB", level="DEBUG")

    world = WorldStorage()
    world.load_all_agents()

    if not world.agents:
        logger.error("No agents found. Run 'python scripts/init_world.py' first.")
        sys.exit(1)

    progress = world.load_progress()
    start_day = args.start_day or progress.current_day
    end_day = start_day + args.days - 1

    logger.info(f"Starting simulation: days {start_day}-{end_day}, seed={args.seed}")

    orchestrator = Orchestrator(world, seed=args.seed)
    asyncio.run(orchestrator.run(start_day, end_day))

    logger.info("Simulation complete!")


if __name__ == "__main__":
    main()
