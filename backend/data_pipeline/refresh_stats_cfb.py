"""Load the current season's CFB team-game PPA into team_game_stats.

The rolling EPA form features read team_game_stats. Without this step the
in-progress CFB season has no rows, so "last 5 games" silently falls back to
last season and then to nothing.

Usage: python -m data_pipeline.refresh_stats_cfb [--season 2026]
"""

import argparse
import sys

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, Game
from data_pipeline.backfill_cfb import backfill_team_game_stats


def has_final_games(db: Session, season: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(Game)
        .where(
            Game.sport == SPORT_CFB,
            Game.season == season,
            Game.home_score.is_not(None),
            Game.away_score.is_not(None),
        )
    )
    return bool(count)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("WARNING: CFBD_API_KEY is not set; CFB stats not refreshed.")
        sys.exit(0)

    with session_scope() as db:
        if not has_final_games(db, args.season):
            print(f"cfb stats refresh: no final games for {args.season} yet, skipping.")
            return
        try:
            rows = backfill_team_game_stats(db, args.season)
        except requests.RequestException as exc:
            print(f"cfb stats refresh failed: {exc}")
            sys.exit(1)
    print(f"cfb stats refresh: upserted {rows} team_game_stats rows for {args.season}")


if __name__ == "__main__":
    main()
