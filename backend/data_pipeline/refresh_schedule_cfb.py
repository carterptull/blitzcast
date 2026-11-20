"""Sync the current CFB season's schedule (scores, TBD kickoffs firming up).

Usage: python -m data_pipeline.refresh_schedule_cfb [--season 2026]
"""

import argparse
import sys

import pandas as pd

from app.config import get_settings
from app.db import session_scope
from app.season import current_season
from data_pipeline import cfbd
from data_pipeline.cfb_games_loader import upsert_games


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_season("cfb"))
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("CFBD_API_KEY is not set in backend/.env — skipping CFB schedule sync.")
        sys.exit(0)

    frames = [
        cfbd.load_games(args.season),
        cfbd.load_games(args.season, "postseason", classification="fbs"),
    ]
    frames = [f for f in frames if not f.empty]
    games = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if games.empty:
        print(f"no CFB schedule rows found for {args.season}")
        return
    with session_scope() as db:
        written, skipped = upsert_games(db, games)
    print(f"cfb schedule sync: upserted {written} games for {args.season} (skipped {skipped})")


if __name__ == "__main__":
    main()
