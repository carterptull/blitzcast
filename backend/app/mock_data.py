"""Fixture data served when BLITZCAST_MOCK=1, so the frontend can develop
against the real contract before the DB/model exist."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import (
    FactorOut,
    GameSummary,
    GameTeam,
    OddsOut,
    PredictionOut,
    ScheduleOut,
    TeamDetail,
    TeamOut,
    VenueOut,
    WeatherOut,
    WeekOut,
)
from data_pipeline.team_names import logo_url, nickname

SEEDS_DIR = Path(__file__).resolve().parent.parent / "data_pipeline" / "seeds"

_MOCK_GAMES = [
    {
        "game_id": "2026_01_BUF_KC",
        "week": 1,
        "kickoff": datetime(2026, 9, 10, 20, 20, tzinfo=UTC),
        "home": "KC",
        "away": "BUF",
        "is_primetime": True,
        "is_divisional": False,
        "home_win_prob": 0.63,
        "venue": {
            "name": "GEHA Field at Arrowhead Stadium",
            "city": "Kansas City",
            "is_dome": False,
        },
        "odds": {"spread_home": -2.5, "moneyline_home": -140, "moneyline_away": 120, "total": 48.5},
        "weather": {"temp_f": 74.0, "wind_mph": 8.0, "precipitation": False, "conditions": "Clear"},
        "factors": [
            {"label": "Team rating (Elo) edge", "value": 0.14, "direction": "home"},
            {"label": "Offensive EPA/play, last 5 games", "value": 0.09, "direction": "home"},
            {"label": "Rest advantage", "value": -0.04, "direction": "away"},
            {"label": "Betting-market win probability", "value": 0.06, "direction": "home"},
        ],
        "narrative": (
            "Folks, the numbers love Kansas City tonight — a 63 percent shot at "
            "home behind a rating edge worth fourteen points of probability! "
            "Buffalo counters with a rest advantage, but the Chiefs' offense has "
            "been humming over its last five games. Under the lights at "
            "Arrowhead, the model says the home crowd gets the last word."
        ),
    },
    {
        "game_id": "2026_01_SF_LA",
        "week": 1,
        "kickoff": datetime(2026, 9, 11, 0, 35, tzinfo=UTC),
        "home": "LA",
        "away": "SF",
        "is_primetime": True,
        "is_divisional": True,
        "home_win_prob": None,
        "venue": {"name": "SoFi Stadium", "city": "Inglewood", "is_dome": True},
        "odds": {"spread_home": 3.0, "moneyline_home": -180, "moneyline_away": 150, "total": 48.5},
        "weather": None,
        "factors": [],
        "narrative": None,
    },
    {
        "game_id": "2026_02_KC_DEN",
        "week": 2,
        "kickoff": datetime(2026, 9, 20, 20, 25, tzinfo=UTC),
        "home": "DEN",
        "away": "KC",
        "is_primetime": False,
        "is_divisional": True,
        "home_win_prob": 0.41,
        "venue": {"name": "Empower Field at Mile High", "city": "Denver", "is_dome": False},
        "odds": {"spread_home": 2.5, "moneyline_home": 115, "moneyline_away": -135, "total": 44.0},
        "weather": {"temp_f": 68.0, "wind_mph": 6.0, "precipitation": False, "conditions": "Sunny"},
        "factors": [
            {"label": "Team rating (Elo) edge", "value": -0.11, "direction": "away"},
            {"label": "Betting-market win probability", "value": -0.05, "direction": "away"},
            {"label": "Divisional rivalry game", "value": 0.02, "direction": "home"},
            {"label": "Kickoff temperature", "value": 0.01, "direction": "home"},
        ],
        "narrative": None,
    },
]

MOCK_SEASON = 2026


def _teams() -> list[dict]:
    return json.loads((SEEDS_DIR / "teams.json").read_text(encoding="utf-8"))


def _team_name(abbr: str) -> str:
    for t in _teams():
        if t["abbr"] == abbr:
            return t["name"]
    return abbr


def list_teams() -> list[TeamOut]:
    return [
        TeamOut(
            id=i + 1,
            abbr=t["abbr"],
            name=t["name"],
            conference=t["conference"],
            division=t["division"],
            logo_url=logo_url(t["abbr"]),
        )
        for i, t in enumerate(_teams())
    ]


def _summary(g: dict) -> GameSummary:
    return GameSummary(
        game_id=g["game_id"],
        kickoff=g["kickoff"],
        home=GameTeam(abbr=g["home"], name=nickname(_team_name(g["home"]))),
        away=GameTeam(abbr=g["away"], name=nickname(_team_name(g["away"]))),
        is_primetime=g["is_primetime"],
        status="scheduled",
        has_prediction=g["home_win_prob"] is not None,
        home_win_prob=g["home_win_prob"],
    )


def get_schedule(season: int) -> ScheduleOut:
    games = [g for g in _MOCK_GAMES if season == MOCK_SEASON]
    weeks: dict[int, list[GameSummary]] = {}
    for g in games:
        weeks.setdefault(g["week"], []).append(_summary(g))
    return ScheduleOut(
        season=season, weeks=[WeekOut(week=w, games=weeks[w]) for w in sorted(weeks)]
    )


def get_games(season: int, week: int) -> list[GameSummary]:
    if season != MOCK_SEASON:
        return []
    return [_summary(g) for g in _MOCK_GAMES if g["week"] == week]


def get_prediction_detail(game_id: str) -> PredictionOut | None:
    g = next((g for g in _MOCK_GAMES if g["game_id"] == game_id), None)
    if g is None:
        return None
    prob = g["home_win_prob"]
    return PredictionOut(
        game_id=g["game_id"],
        season=MOCK_SEASON,
        week=g["week"],
        kickoff=g["kickoff"],
        venue=VenueOut(**g["venue"]),
        is_primetime=g["is_primetime"],
        is_divisional=g["is_divisional"],
        home=TeamDetail(
            abbr=g["home"],
            name=nickname(_team_name(g["home"])),
            record="0-0",
            logo_url=logo_url(g["home"]),
            win_prob=prob,
        ),
        away=TeamDetail(
            abbr=g["away"],
            name=nickname(_team_name(g["away"])),
            record="0-0",
            logo_url=logo_url(g["away"]),
            win_prob=None if prob is None else round(1 - prob, 4),
        ),
        odds=OddsOut(**g["odds"]) if g["odds"] else None,
        weather=WeatherOut(**g["weather"]) if g["weather"] else None,
        factors=[FactorOut(**f) for f in g["factors"]],
        narrative=g["narrative"],
        model_version="0.1.0-mock" if prob is not None else None,
        predicted_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC) if prob is not None else None,
        prediction_status="available" if prob is not None else "pending",
    )
