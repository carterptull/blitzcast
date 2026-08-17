"""Replay results and persist weekly Elo snapshots to team_ratings.

Each row is a team's rating *entering* (season, week). Snapshots are
per-sport: recomputing one sport never touches the other's rows.

Usage: python -m ml.compute_ratings [--sport nfl|cfb]
"""

import argparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL, Game, Team, TeamRating
from ml import elo


def compute_ratings(db: Session, sport: str = SPORT_NFL) -> int:
    teams = db.scalars(select(Team).where(Team.sport == sport)).all()
    abbrs = {t.team_id: t.abbr for t in teams}
    tiers = {t.abbr: t.tier for t in teams if t.tier}
    games = db.scalars(
        # Coalesced: NULL kickoffs (CFB TBD) sort last otherwise, replaying
        # out of order and firing season regression repeatedly.
        select(Game)
        .where(Game.sport == sport)
        .order_by(func.coalesce(Game.kickoff_time, Game.game_date))
    ).all()

    book = elo.EloBook(config=elo.config_for(sport), tiers=tiers)
    snapshots: dict[tuple[int, int, int], float] = {}
    for g in games:
        home, away = abbrs[g.home_team_id], abbrs[g.away_team_id]
        elo_home, elo_away = book.pre_game(g.season, home, away)
        snapshots[(g.home_team_id, g.season, g.week)] = elo_home
        snapshots[(g.away_team_id, g.season, g.week)] = elo_away
        if g.home_score is not None and g.away_score is not None:
            book.record_result(g.season, home, away, g.home_score, g.away_score)

    db.execute(delete(TeamRating).where(TeamRating.sport == sport))
    for (team_id, season, week), rating in snapshots.items():
        db.add(
            TeamRating(
                sport=sport, team_id=team_id, season=season, week=week, elo_rating=rating
            )
        )
    return len(snapshots)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL

    with session_scope() as db:
        count = compute_ratings(db, sport)
        print(f"team_ratings[{sport}]: wrote {count} weekly snapshots")


if __name__ == "__main__":
    main()
