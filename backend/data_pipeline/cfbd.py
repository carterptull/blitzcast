"""Thin wrapper around the CollegeFootballData REST API.

Keeps the source swappable: everything downstream consumes pandas
DataFrames. One small function per endpoint so shape drift is a
one-line fix. Field names follow the CFBD v2 API (camelCase).
"""

import pandas as pd
import requests

from app.config import get_settings

BASE_URL = "https://api.collegefootballdata.com"


def _get(path: str, params: dict | None = None) -> list[dict]:
    key = get_settings().cfbd_api_key
    if not key:
        raise RuntimeError("CFBD_API_KEY is not set in backend/.env")
    resp = requests.get(
        f"{BASE_URL}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def load_fbs_teams(year: int) -> pd.DataFrame:
    return pd.json_normalize(_get("/teams/fbs", {"year": year}))


def load_fcs_teams(year: int) -> pd.DataFrame:
    # [VERIFY] /teams has no classification filter param; filter client-side.
    df = pd.json_normalize(_get("/teams", {"year": year}))
    return df[df["classification"].str.lower() == "fcs"].reset_index(drop=True)


def load_venues() -> pd.DataFrame:
    return pd.json_normalize(_get("/venues"))


def load_games(year: int, season_type: str = "regular") -> pd.DataFrame:
    return pd.json_normalize(_get("/games", {"year": year, "seasonType": season_type}))


def load_lines(year: int, season_type: str = "regular") -> pd.DataFrame:
    """Betting lines flattened to one row per (game, provider)."""
    rows = []
    for game in _get("/lines", {"year": year, "seasonType": season_type}):
        for line in game.get("lines") or []:
            rows.append(
                {
                    "game_id": game["id"],
                    "provider": line.get("provider"),
                    "spread": line.get("spread"),
                    "over_under": line.get("overUnder"),
                    "home_moneyline": line.get("homeMoneyline"),
                    "away_moneyline": line.get("awayMoneyline"),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["game_id", "provider", "spread", "over_under", "home_moneyline", "away_moneyline"],
    )


def load_rankings(year: int, season_type: str = "regular") -> pd.DataFrame:
    """Poll rankings flattened to one row per (week, poll, team)."""
    rows = []
    for entry in _get("/rankings", {"year": year, "seasonType": season_type}):
        for poll in entry.get("polls") or []:
            for rank in poll.get("ranks") or []:
                rows.append(
                    {
                        "season": entry["season"],
                        "week": entry["week"],
                        "poll": poll.get("poll"),
                        "school": rank.get("school"),
                        "rank": rank.get("rank"),
                    }
                )
    return pd.DataFrame(rows, columns=["season", "week", "poll", "school", "rank"])


def load_team_game_ppa(year: int, season_type: str = "regular") -> pd.DataFrame:
    """Team-game PPA (CFBD's EPA-per-play analogue), one row per (game, team)."""
    df = pd.json_normalize(_get("/ppa/games", {"year": year, "seasonType": season_type}))
    # [VERIFY] nested field names offense.overall / defense.overall.
    return df.rename(
        columns={
            "gameId": "game_id",
            "offense.overall": "ppa_offense",
            "defense.overall": "ppa_defense",
        }
    )
