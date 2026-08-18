"""Upsert CFBD game rows into the games table (shared by backfill_cfb and
the weekly CFB schedule refresh).

FCS-vs-FCS and unresolvable-team games are dropped here — the single
chokepoint for the scope rule, so odds/weather can never attach to them.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SPORT_CFB, Game, Stadium, Team

ET = ZoneInfo("America/New_York")


def should_skip_game(home_tier: str | None, away_tier: str | None) -> bool:
    """Scope rule: skip FCS-vs-FCS and games with an unresolvable team."""
    if home_tier is None or away_tier is None:
        return True
    return home_tier == "FCS" and away_tier == "FCS"


def cfb_team_map(db: Session) -> dict[str, Team]:
    """CFB teams keyed by school name (CFBD `school` is stored as Team.name)."""
    return {t.name: t for t in db.scalars(select(Team).where(Team.sport == SPORT_CFB))}


def field(row: dict, *names):
    for n in names:
        value = row.get(n)
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            return value
    return None


def _start(row: dict) -> datetime | None:
    raw = field(row, "startDate", "start_date")
    if not raw:
        return None
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _is_primetime(kickoff: datetime | None) -> bool:
    return kickoff is not None and kickoff.astimezone(ET).hour >= 19


def upsert_games(db: Session, games: pd.DataFrame) -> tuple[int, int]:
    """Idempotent upsert keyed on `cfb_<cfbd_id>`. Returns (written, skipped)."""
    teams = cfb_team_map(db)
    stadium_by_name = {s.name: s.stadium_id for s in db.scalars(select(Stadium))}
    ids = [f"cfb_{int(i)}" for i in games["id"]]
    existing = {g.game_id: g for g in db.scalars(select(Game).where(Game.game_id.in_(ids)))}

    written = skipped = 0
    for row in games.to_dict("records"):
        home_name = field(row, "homeTeam", "home_team")
        away_name = field(row, "awayTeam", "away_team")
        home = teams.get(home_name)
        away = teams.get(away_name)
        if should_skip_game(home.tier if home else None, away.tier if away else None):
            if (home and home.tier == "FBS") or (away and away.tier == "FBS"):
                print(f"skipping cfb game {row.get('id')}: unresolved opponent "
                      f"({away_name!r} at {home_name!r})")
            skipped += 1
            continue
        start = _start(row)
        if start is None:
            skipped += 1
            continue
        tbd = bool(field(row, "startTimeTBD", "start_time_tbd"))
        gid = f"cfb_{int(row['id'])}"
        game = existing.get(gid)
        if game is None:
            game = Game(game_id=gid, sport=SPORT_CFB)
            db.add(game)
            existing[gid] = game
        game.season = int(row["season"])
        game.week = int(row["week"])
        game.game_date = start.astimezone(ET).date()
        game.kickoff_time = None if tbd else start
        game.home_team_id = home.team_id
        game.away_team_id = away.team_id
        game.stadium_id = stadium_by_name.get(field(row, "venue"))
        game.is_primetime = _is_primetime(game.kickoff_time)
        # For CFB, "divisional" means same-conference.
        game.is_divisional = bool(field(row, "conferenceGame", "conference_game"))
        home_pts = field(row, "homePoints", "home_points")
        away_pts = field(row, "awayPoints", "away_points")
        game.home_score = None if home_pts is None else int(home_pts)
        game.away_score = None if away_pts is None else int(away_pts)
        completed = field(row, "completed")
        if completed is None:
            completed = home_pts is not None
        game.status = "final" if completed else "scheduled"
        written += 1
    db.flush()
    return written, skipped
