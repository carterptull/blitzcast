"""Pull current NFL odds from The Odds API into the odds table.

One API call returns every upcoming game, so one run per day stays far
inside the free tier (500 requests/month).

Usage: python -m data_pipeline.refresh_odds
"""

import sys
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Game, Odds
from data_pipeline.games_loader import team_id_map
from data_pipeline.team_names import to_abbr

ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
SOURCE = "the-odds-api"


def _consensus(event: dict, home_abbr: str, away_abbr: str) -> dict:
    """Take the first bookmaker that carries each market."""
    out: dict = {}
    home_name, away_name = event["home_team"], event["away_team"]
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            key = market["key"]
            if key in out:
                continue
            outcomes = {o["name"]: o for o in market.get("outcomes", [])}
            if key == "h2h" and home_name in outcomes and away_name in outcomes:
                out["h2h"] = (outcomes[home_name]["price"], outcomes[away_name]["price"])
            elif key == "spreads" and home_name in outcomes:
                out["spreads"] = outcomes[home_name].get("point")
            elif key == "totals" and market.get("outcomes"):
                out["totals"] = market["outcomes"][0].get("point")
    return out


def main() -> None:
    settings = get_settings()
    if not settings.odds_api_key:
        print("ODDS_API_KEY is not set in backend/.env — skipping odds refresh.")
        sys.exit(0)

    resp = requests.get(
        ODDS_URL,
        params={
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "apiKey": settings.odds_api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json()
    remaining = resp.headers.get("x-requests-remaining")

    now = datetime.now(UTC)
    upserted = 0
    with session_scope() as db:
        ids = team_id_map(db)
        window_games = db.scalars(
            select(Game).where(
                Game.kickoff_time >= now - timedelta(hours=6),
                Game.kickoff_time <= now + timedelta(days=14),
            )
        ).all()
        by_matchup = {(g.home_team_id, g.away_team_id): g for g in window_games}

        for event in events:
            try:
                home = to_abbr(event["home_team"])
                away = to_abbr(event["away_team"])
            except KeyError as exc:
                print(f"skipping event, unknown team: {exc}")
                continue
            game = by_matchup.get((ids[home], ids[away]))
            if game is None:
                continue
            markets = _consensus(event, home, away)
            odds = db.scalar(
                select(Odds).where(Odds.game_id == game.game_id, Odds.source == SOURCE)
            )
            if odds is None:
                odds = Odds(game_id=game.game_id, source=SOURCE)
                db.add(odds)
            h2h = markets.get("h2h")
            if h2h:
                odds.moneyline_home, odds.moneyline_away = int(h2h[0]), int(h2h[1])
            if markets.get("spreads") is not None:
                odds.spread_home = float(markets["spreads"])
            if markets.get("totals") is not None:
                odds.total = float(markets["totals"])
            odds.captured_at = now
            upserted += 1

    print(f"odds refresh: upserted {upserted} games (requests remaining: {remaining})")


if __name__ == "__main__":
    main()
