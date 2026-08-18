"""Pull current odds from The Odds API into the odds table.

One API call returns every upcoming game for a sport, so one run per day
per sport stays far inside the free tier (500 requests/month).

Usage: python -m data_pipeline.refresh_odds [--sport nfl|cfb]
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import and_, or_, select

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL, Game, Odds
from data_pipeline.cfb_team_names import cfb_to_abbr
from data_pipeline.games_loader import team_id_map
from data_pipeline.team_names import to_abbr

ODDS_URL = "https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
SPORT_KEYS = {"nfl": "americanfootball_nfl", "cfb": "americanfootball_ncaaf"}
SOURCE = "the-odds-api"


def book_spread_to_home(point: float) -> float:
    """Books quote negative when home is favored; storage follows nflverse
    (positive = home favored), so the sign flips on the way in."""
    return -float(point)


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL
    resolve = cfb_to_abbr if args.sport == "cfb" else to_abbr

    settings = get_settings()
    if not settings.odds_api_key:
        print("ODDS_API_KEY is not set in backend/.env — skipping odds refresh.")
        sys.exit(0)

    resp = requests.get(
        ODDS_URL.format(sport_key=SPORT_KEYS[args.sport]),
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
    # Starts at now, not earlier: reaching back would capture in-play lines.
    lo, hi = now, now + timedelta(days=14)
    upserted = 0
    with session_scope() as db:
        ids = team_id_map(db, sport)
        # NULL kickoff (TBD) falls back to game_date so those games still match.
        window_games = db.scalars(
            select(Game).where(
                Game.sport == sport,
                or_(
                    and_(Game.kickoff_time >= lo, Game.kickoff_time <= hi),
                    and_(
                        Game.kickoff_time.is_(None),
                        Game.game_date >= lo.date(),
                        Game.game_date <= hi.date(),
                    ),
                ),
            )
        ).all()
        by_matchup = {(g.home_team_id, g.away_team_id): g for g in window_games}
        unmatched = 0

        for event in events:
            try:
                home = resolve(event["home_team"])
                away = resolve(event["away_team"])
            except KeyError as exc:
                print(f"skipping event, unknown team: {exc}")
                continue
            game = by_matchup.get((ids.get(home), ids.get(away)))
            if game is None:
                unmatched += 1
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
                odds.spread_home = book_spread_to_home(markets["spreads"])
            if markets.get("totals") is not None:
                odds.total = float(markets["totals"])
            odds.captured_at = now
            upserted += 1

    print(f"odds refresh ({args.sport}): upserted {upserted} games, "
          f"{unmatched} unmatched (requests remaining: {remaining})")
    if events and upserted == 0:
        # Silence here would let a broken alias map feed stale market data
        # into predictions while the job still exits 0.
        print(
            f"WARNING: matched none of {len(events)} events to scheduled games; "
            "check the team-name alias map."
        )


if __name__ == "__main__":
    main()
