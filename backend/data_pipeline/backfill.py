"""Historical backfill: schedules -> games, play-by-play -> team_game_stats,
injuries, and kickoff weather actuals (from nflverse schedules).

Usage: python -m data_pipeline.backfill [--start 2021] [--end 2026]
"""

import argparse

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Game, Injury, TeamGameStat, Weather
from data_pipeline import nflverse
from data_pipeline.games_loader import team_id_map, upsert_games
from data_pipeline.team_names import to_abbr


def backfill_team_game_stats(db: Session, seasons: list[int]) -> int:
    pbp = nflverse.load_pbp(seasons)
    plays = pbp[pbp["epa"].notna() & pbp["posteam"].notna()]

    off = plays.groupby(["game_id", "posteam"]).agg(
        epa_offense=("epa", "mean"),
        yards=("yards_gained", "sum"),
        turnovers_fum=("fumble_lost", "sum"),
        turnovers_int=("interception", "sum"),
    )
    def_ = plays.groupby(["game_id", "defteam"]).agg(epa_defense=("epa", "mean"))
    def_.index.names = ["game_id", "posteam"]
    stats = off.join(def_, how="outer").reset_index()
    stats["turnovers"] = stats["turnovers_fum"].fillna(0) + stats["turnovers_int"].fillna(0)

    ids = team_id_map(db)
    games = {
        g.game_id: g
        for g in db.scalars(select(Game).where(Game.season.in_(seasons)))
    }

    game_ids = [gid for gid in stats["game_id"].unique() if gid in games]
    db.execute(delete(TeamGameStat).where(TeamGameStat.game_id.in_(game_ids)))

    rows = 0
    for row in stats.itertuples(index=False):
        game = games.get(row.game_id)
        if game is None:
            continue
        team_id = ids[to_abbr(row.posteam)]
        points = (
            game.home_score if team_id == game.home_team_id else game.away_score
        )
        db.add(
            TeamGameStat(
                game_id=row.game_id,
                team_id=team_id,
                points=points,
                yards=None if pd.isna(row.yards) else float(row.yards),
                epa_offense=None if pd.isna(row.epa_offense) else float(row.epa_offense),
                epa_defense=None if pd.isna(row.epa_defense) else float(row.epa_defense),
                turnovers=int(row.turnovers),
            )
        )
        rows += 1
    db.flush()
    return rows


def backfill_injuries(db: Session, seasons: list[int]) -> int:
    inj = nflverse.load_injuries(seasons)
    ids = team_id_map(db)

    game_by_week_team: dict[tuple[int, int, int], str] = {}
    for g in db.scalars(select(Game).where(Game.season.in_(seasons))):
        game_by_week_team[(g.season, g.week, g.home_team_id)] = g.game_id
        game_by_week_team[(g.season, g.week, g.away_team_id)] = g.game_id

    records = []
    seen = set()
    for row in inj.itertuples(index=False):
        try:
            team_id = ids[to_abbr(row.team)]
        except KeyError:
            continue
        game_id = game_by_week_team.get((int(row.season), int(row.week), team_id))
        if game_id is None or not row.full_name:
            continue
        key = (game_id, team_id, row.full_name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            Injury(
                game_id=game_id,
                team_id=team_id,
                player_name=row.full_name,
                position=row.position,
                status=row.report_status,
                report_date=None if pd.isna(row.date_modified) else row.date_modified.date(),
            )
        )

    game_ids = list({r.game_id for r in records})
    db.execute(delete(Injury).where(Injury.game_id.in_(game_ids)))
    db.add_all(records)
    db.flush()
    return len(records)


def backfill_weather(db: Session, schedules: pd.DataFrame) -> int:
    """Kickoff actuals recorded by nflverse for played outdoor games."""
    played = schedules[schedules["temp"].notna()]
    games = {g.game_id for g in db.scalars(select(Game))}
    existing = {w.game_id: w for w in db.scalars(select(Weather))}

    rows = 0
    for row in played.itertuples(index=False):
        if row.game_id not in games:
            continue
        game = db.get(Game, row.game_id)
        w = existing.get(row.game_id)
        if w is None:
            w = Weather(game_id=row.game_id)
            db.add(w)
            existing[row.game_id] = w
        w.temp_f = float(row.temp)
        w.wind_mph = None if pd.isna(row.wind) else float(row.wind)
        w.precipitation = None
        w.conditions = None
        w.captured_at = game.kickoff_time
        rows += 1
    db.flush()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2021)
    parser.add_argument("--end", type=int, default=2026)
    args = parser.parse_args()
    seasons = list(range(args.start, args.end + 1))

    with session_scope() as db:
        schedules = nflverse.load_schedules(seasons)
        n_games = upsert_games(db, schedules)
        print(f"games: upserted {n_games}")
        played = [s for s in seasons if s <= 2025]
        n_stats = backfill_team_game_stats(db, played)
        print(f"team_game_stats: upserted {n_stats}")
        n_inj = backfill_injuries(db, played)
        print(f"injuries: upserted {n_inj}")
        n_wx = backfill_weather(db, schedules)
        print(f"weather: upserted {n_wx}")


if __name__ == "__main__":
    main()
