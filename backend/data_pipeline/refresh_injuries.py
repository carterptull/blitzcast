"""Refresh current injuries from ESPN's (unofficial) injuries endpoint,
falling back to nflverse injury reports if ESPN is unavailable.

Injuries are attached to each team's next scheduled game.

Usage: python -m data_pipeline.refresh_injuries [--season 2026]
"""

import argparse
from datetime import UTC, datetime

import requests
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Game, Injury
from data_pipeline import nflverse
from data_pipeline.games_loader import team_id_map
from data_pipeline.team_names import to_abbr

ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"


def _next_game_by_team(db: Session, season: int) -> dict[int, str]:
    now = datetime.now(UTC)
    games = db.scalars(
        select(Game)
        .where(Game.season == season, Game.kickoff_time >= now)
        .order_by(Game.kickoff_time)
    ).all()
    next_game: dict[int, str] = {}
    for g in games:
        next_game.setdefault(g.home_team_id, g.game_id)
        next_game.setdefault(g.away_team_id, g.game_id)
    return next_game


def fetch_espn() -> list[dict]:
    """Returns [{team, player_name, position, status, report_date}, ...]."""
    resp = requests.get(ESPN_INJURIES_URL, params={"limit": 2000}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    rows: list[dict] = []
    for team_blob in payload.get("injuries", []):
        team_name = team_blob.get("displayName") or team_blob.get("shortDisplayName")
        for item in team_blob.get("injuries", []):
            athlete = item.get("athlete", {})
            rows.append(
                {
                    "team": team_name,
                    "player_name": athlete.get("displayName"),
                    "position": (athlete.get("position") or {}).get("abbreviation"),
                    "status": item.get("status"),
                    "report_date": (item.get("date") or "")[:10] or None,
                }
            )
    return rows


def fetch_nflverse(season: int) -> list[dict]:
    inj = nflverse.load_injuries([season])
    if inj.empty:
        return []
    latest_week = int(inj["week"].max())
    inj = inj[inj["week"] == latest_week]
    return [
        {
            "team": r.team,
            "player_name": r.full_name,
            "position": r.position,
            "status": r.report_status,
            "report_date": None if r.date_modified is None else str(r.date_modified.date()),
        }
        for r in inj.itertuples(index=False)
    ]


def upsert_injuries(db: Session, rows: list[dict], season: int) -> int:
    ids = team_id_map(db)
    next_game = _next_game_by_team(db, season)
    records = []
    seen = set()
    for row in rows:
        if not row.get("player_name") or not row.get("team"):
            continue
        try:
            team_id = ids[to_abbr(row["team"])]
        except KeyError:
            continue
        game_id = next_game.get(team_id)
        if game_id is None:
            continue
        key = (game_id, team_id, row["player_name"])
        if key in seen:
            continue
        seen.add(key)
        report_date = row.get("report_date")
        records.append(
            Injury(
                game_id=game_id,
                team_id=team_id,
                player_name=row["player_name"],
                position=row.get("position"),
                status=row.get("status"),
                report_date=None if not report_date else datetime.fromisoformat(report_date).date(),
            )
        )
    game_ids = list({r.game_id for r in records})
    if game_ids:
        db.execute(delete(Injury).where(Injury.game_id.in_(game_ids)))
    db.add_all(records)
    db.flush()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    try:
        rows = fetch_espn()
        source = "espn"
    except Exception as exc:
        print(f"ESPN injuries fetch failed ({exc}); falling back to nflverse")
        rows = fetch_nflverse(args.season)
        source = "nflverse"

    if not rows:
        print("injury refresh: no injury rows available yet — nothing to do")
        return

    with session_scope() as db:
        n = upsert_injuries(db, rows, args.season)
    print(f"injury refresh: upserted {n} rows from {source}")


if __name__ == "__main__":
    main()
