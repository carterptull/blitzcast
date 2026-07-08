"""Sync the current season's schedule (scores, flexed kickoffs, byes).

Usage: python -m data_pipeline.refresh_schedule [--season 2026]
"""

import argparse

from app.db import session_scope
from data_pipeline import nflverse
from data_pipeline.games_loader import upsert_games


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    schedules = nflverse.load_schedules([args.season])
    if schedules.empty:
        print(f"no schedule rows found for {args.season}")
        return
    with session_scope() as db:
        n = upsert_games(db, schedules)
    print(f"schedule sync: upserted {n} games for {args.season}")


if __name__ == "__main__":
    main()
