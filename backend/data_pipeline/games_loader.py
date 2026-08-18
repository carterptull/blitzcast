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


def _kickoff_utc(gameday: str, gametime: str | None) -> datetime | None:
    if not gametime:
        return None
    day = date.fromisoformat(gameday)
    hour, minute = (int(x) for x in gametime.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=ET).astimezone(UTC)


def _is_primetime(gametime: str | None) -> bool:
    return bool(gametime) and gametime >= "19:00"


def _opt(value):
    return None if pd.isna(value) else value


def _placeholder_weeks(schedules: pd.DataFrame) -> set[tuple[int, int]]:
    """(season, week) pairs where every game shares one gametime string.

    A real, determined NFL week always spans multiple broadcast windows
    (early/late/primetime) once it has more than a couple of games; nflverse
    fills a schedule it hasn't finalized real broadcast times for with one
    repeated placeholder string (observed: "13:00") instead of leaving the
    field blank, so per-row nulls can't be used to detect this."""
    placeholders = set()
    for (season, week), group in schedules.groupby(["season", "week"]):
        times = group["gametime"].dropna().unique()
        if len(group) > 2 and len(times) == 1:
            placeholders.add((int(season), int(week)))
    return placeholders


def upsert_games(db: Session, schedules: pd.DataFrame) -> int:
    """Idempotent upsert keyed on nflverse game_id. Returns rows written."""
    ids = team_id_map(db)
    stadium_by_team = {
        t.team_id: t.stadium_id for t in db.scalars(select(Team))
    }
    existing = {g.game_id: g for g in db.scalars(select(Game))}
    placeholder_weeks = _placeholder_weeks(schedules)

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
        is_placeholder_week = (int(row.season), int(row.week)) in placeholder_weeks
        if is_placeholder_week:
            game.kickoff_time = None
        else:
            game.kickoff_time = _kickoff_utc(row.gameday, _opt(row.gametime))
        game.home_team_id = ids[home]
        game.away_team_id = ids[away]
        game.stadium_id = (
            stadium_by_team.get(ids[home]) if row.location == "Home" else None
        )
        game.is_primetime = False if is_placeholder_week else _is_primetime(_opt(row.gametime))
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
