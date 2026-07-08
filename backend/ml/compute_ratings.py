"""Replay results and persist weekly Elo snapshots to team_ratings.

Each row is a team's rating *entering* (season, week).

Usage: python -m ml.compute_ratings
"""

from sqlalchemy import delete, select

from app.db import session_scope
from app.models import Game, Team, TeamRating
from ml.elo import EloBook


def main() -> None:
    with session_scope() as db:
        teams = {t.team_id: t.abbr for t in db.scalars(select(Team))}
        games = db.scalars(select(Game).order_by(Game.kickoff_time)).all()

        book = EloBook()
        snapshots: dict[tuple[int, int, int], float] = {}
        for g in games:
            home, away = teams[g.home_team_id], teams[g.away_team_id]
            elo_home, elo_away = book.pre_game(g.season, home, away)
            snapshots[(g.home_team_id, g.season, g.week)] = elo_home
            snapshots[(g.away_team_id, g.season, g.week)] = elo_away
            if g.home_score is not None:
                book.record_result(g.season, home, away, g.home_score, g.away_score)

        db.execute(delete(TeamRating))
        for (team_id, season, week), rating in snapshots.items():
            db.add(
                TeamRating(team_id=team_id, season=season, week=week, elo_rating=rating)
            )
        print(f"team_ratings: wrote {len(snapshots)} weekly snapshots")


if __name__ == "__main__":
    main()
