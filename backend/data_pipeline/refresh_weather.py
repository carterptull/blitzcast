"""Fetch kickoff weather (forecast or historical) from the Visual Crossing
Timeline API for upcoming outdoor games. Domed/roofed and no-stadium
(international) games are skipped.

Usage: python -m data_pipeline.refresh_weather [--days 8] [--sport nfl|cfb]
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL, Game, Weather

BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"


def fetch_day(lat: float, lon: float, day: str, api_key: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/{lat},{lon}/{day}",
        params={"key": api_key, "unitGroup": "us", "include": "hours"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _kickoff_hour(payload: dict, kickoff_utc: datetime) -> dict | None:
    """Pick the forecast hour closest to kickoff (API returns local hours
    with epoch seconds)."""
    days = payload.get("days") or []
    if not days:
        return None
    hours = days[0].get("hours") or []
    if not hours:
        return days[0]
    target = kickoff_utc.timestamp()
    return min(hours, key=lambda h: abs(h.get("datetimeEpoch", 0) - target))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=8, help="look-ahead window")
    # Defaults to NFL: a full FBS slate is ~70 games per run against a free tier.
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL

    settings = get_settings()
    if not settings.visual_crossing_api_key:
        print("VISUAL_CROSSING_API_KEY is not set in backend/.env — skipping weather refresh.")
        sys.exit(0)

    now = datetime.now(UTC)
    updated = skipped = failed = 0
    with session_scope() as db:
        games = db.scalars(
            select(Game)
            .options(joinedload(Game.stadium))
            .where(
                Game.sport == sport,
                Game.kickoff_time >= now,
                Game.kickoff_time <= now + timedelta(days=args.days),
            )
        ).all()
        for game in games:
            stadium = game.stadium
            if stadium is None or stadium.is_dome:
                skipped += 1
                continue
            try:
                payload = fetch_day(
                    stadium.lat,
                    stadium.lon,
                    game.game_date.isoformat(),
                    settings.visual_crossing_api_key,
                )
            except requests.RequestException as exc:
                # Commit per game: the quota spent on earlier calls is gone
                # either way, so a late failure must not roll them back.
                print(f"weather refresh: {game.game_id} failed ({exc})")
                failed += 1
                continue
            hour = _kickoff_hour(payload, game.kickoff_time)
            if hour is None:
                continue
            w = db.get(Weather, game.game_id)
            if w is None:
                w = Weather(game_id=game.game_id)
                db.add(w)
            w.temp_f = hour.get("temp")
            w.wind_mph = hour.get("windspeed")
            w.precipitation = (hour.get("precipprob") or 0) >= 40 or (hour.get("precip") or 0) > 0
            w.conditions = hour.get("conditions")
            w.captured_at = now
            db.commit()
            updated += 1

    print(
        f"weather refresh ({args.sport}): updated {updated}, skipped {skipped} "
        f"(dome/international), failed {failed}"
    )


if __name__ == "__main__":
    main()
