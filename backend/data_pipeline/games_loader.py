"""Upsert nflverse schedule rows into the games table (shared by backfill
and the weekly schedule refresh)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SPORT_NFL, Game, Team
from data_pipeline.team_names import to_abbr

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def team_id_map(db: Session, sport: str = SPORT_NFL) -> dict[str, int]:
    return {t.abbr: t.team_id for t in db.scalars(select(Team).where(Team.sport == sport))}


def _kickoff_utc(gameday: str, gametime: str | None) -> datetime:
    day = date.fromisoformat(gameday)
    if gametime:
        hour, minute = (int(x) for x in gametime.split(":"))
    else:
        hour, minute = 13, 0
    return datetime.combine(day, time(hour, minute), tzinfo=ET).astimezone(UTC)


def _is_primetime(gametime: str | None) -> bool:
    return bool(gametime) and gametime >= "19:00"


def _opt(value):
    return None if pd.isna(value) else value


def upsert_games(db: Session, schedules: pd.DataFrame) -> int:
    """Idempotent upsert keyed on nflverse game_id. Returns rows written."""
    ids = team_id_map(db)
    stadium_by_team = {
        t.team_id: t.stadium_id for t in db.scalars(select(Team))
    }
    existing = {g.game_id: g for g in db.scalars(select(Game))}

    count = 0
    for row in schedules.itertuples(index=False):
        home = to_abbr(row.home_team)
        away = to_abbr(row.away_team)
        game = existing.get(row.game_id)
        if game is None:
            game = Game(game_id=row.game_id)
            db.add(game)
            existing[row.game_id] = game
        game.season = int(row.season)
        game.week = int(row.week)
        game.game_date = date.fromisoformat(row.gameday)
        game.kickoff_time = _kickoff_utc(row.gameday, _opt(row.gametime))
        game.home_team_id = ids[home]
        game.away_team_id = ids[away]
        game.stadium_id = (
            stadium_by_team.get(ids[home]) if row.location == "Home" else None
        )
        game.is_primetime = _is_primetime(_opt(row.gametime))
        game.is_divisional = bool(row.div_game)
        home_score = _opt(row.home_score)
        away_score = _opt(row.away_score)
        game.home_score = None if home_score is None else int(home_score)
        game.away_score = None if away_score is None else int(away_score)
        game.status = "final" if home_score is not None else "scheduled"
        game.spread_line = _opt(row.spread_line)
        game.total_line = _opt(row.total_line)
        hml, aml = _opt(row.home_moneyline), _opt(row.away_moneyline)
        game.home_moneyline = None if hml is None else int(hml)
        game.away_moneyline = None if aml is None else int(aml)
        count += 1
    db.flush()
    return count
