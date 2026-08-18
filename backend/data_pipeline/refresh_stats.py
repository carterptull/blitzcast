"""Re-ingest play-by-play into team_game_stats for the current season.

The rolling EPA/turnover form features read team_game_stats. Without a weekly
run they stay empty for the in-progress season, and `rolling(...).mean()`
quietly skips the nulls, so form features decay toward missing a few weeks in
while SHAP keeps labeling them.

Skips cleanly before the season's first game is final: nflreadpy rejects a
season it has no data for, and the weekly orchestrator should not report a
failure every run all summer.

Usage: python -m data_pipeline.refresh_stats [--season 2026]
"""

import argparse

from sqlalchemy import func, select

from app.db import session_scope
from app.models import Game
from data_pipeline.backfill import backfill_team_game_stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    with session_scope() as db:
        played = db.scalar(
            select(func.count())
            .select_from(Game)
            .where(Game.season == args.season, Game.home_score.is_not(None))
        )
        if not played:
            print(f"team_game_stats refresh: no final games for {args.season} yet, skipping.")
            return

        try:
            rows = backfill_team_game_stats(db, [args.season])
        except ValueError as exc:
            print(f"team_game_stats refresh: play-by-play unavailable for {args.season} ({exc})")
            return
    print(f"team_game_stats refresh: upserted {rows} rows for {args.season}")


if __name__ == "__main__":
    main()
