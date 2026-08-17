"""Upsert CFBD poll rankings into poll_ranks (AP preferred, Coaches fallback).

CFBD's regular-season "week N" ranking is the poll published before week N's
games (week 1 = preseason), matching poll_ranks' entering-week semantics, so
it is stored verbatim. Verified against the 2025 AP polls: every ranked team
that lost in week 1 kept its rank in the week 1 poll and fell only in week 2
(Texas #1, lost to Ohio State, #7 the following week). See
tests/test_cfb_polls.py.

Usage: python -m data_pipeline.refresh_polls_cfb [--season 2026]
"""

import argparse
import sys

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, PollRank
from data_pipeline import cfbd
from data_pipeline.cfb_games_loader import cfb_team_map

AP = "AP Top 25"
COACHES = "Coaches Poll"


def upsert_polls(db: Session, rankings: pd.DataFrame) -> int:
    """Delete-then-insert per (sport, season, week): one poll per week, AP
    preferred. Scoped to the weeks actually returned so a partial CFBD
    response cannot wipe weeks it did not include."""
    if rankings.empty:
        return 0
    df = rankings[rankings["poll"].isin([AP, COACHES])]
    if df.empty:
        return 0
    weekly = [
        grp[grp["poll"] == (AP if (grp["poll"] == AP).any() else COACHES)]
        for _, grp in df.groupby(["season", "week"])
    ]
    df = pd.concat(weekly, ignore_index=True)

    teams = cfb_team_map(db)
    for season, week in {(int(r.season), int(r.week)) for r in df.itertuples(index=False)}:
        db.execute(
            delete(PollRank).where(
                PollRank.sport == SPORT_CFB,
                PollRank.season == season,
                PollRank.week == week,
            )
        )
    rows = 0
    for row in df.itertuples(index=False):
        team = teams.get(row.school)
        if team is None:
            print(f"poll refresh: unknown school {row.school!r} — skipping")
            continue
        db.add(
            PollRank(
                sport=SPORT_CFB,
                season=int(row.season),
                week=int(row.week),
                poll=row.poll,
                team_id=team.team_id,
                rank=int(row.rank),
            )
        )
        rows += 1
    db.flush()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("CFBD_API_KEY is not set in backend/.env — skipping CFB polls refresh.")
        sys.exit(0)

    rankings = cfbd.load_rankings(args.season)
    with session_scope() as db:
        n = upsert_polls(db, rankings)
    print(f"polls refresh: upserted {n} poll ranks for {args.season}")


if __name__ == "__main__":
    main()
