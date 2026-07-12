"""Fixture data served when BLITZCAST_MOCK=1, so the frontend can develop
against the real contract before the DB/model exist."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models import SPORT_CFB, SPORT_NFL
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

# Small believable CFB slate: ranked matchup, FBS-vs-FCS, TBD-kickoff game.
_MOCK_CFB_TEAMS = {
    "OSU": {
        "name": "Ohio State", "conference": "Big Ten", "tier": "FBS",
        "rank": 1, "espn_id": 194, "color": "#BB0000", "alt_color": "#666666",
    },
    "TEX": {
        "name": "Texas", "conference": "SEC", "tier": "FBS",
        "rank": 5, "espn_id": 251, "color": "#BF5700", "alt_color": "#FFFFFF",
    },
    "ALA": {
        "name": "Alabama", "conference": "SEC", "tier": "FBS",
        "rank": 4, "espn_id": 333, "color": "#9E1B32", "alt_color": "#FFFFFF",
    },
    "UGA": {
        "name": "Georgia", "conference": "SEC", "tier": "FBS",
        "rank": 2, "espn_id": 61, "color": "#BA0C2F", "alt_color": "#000000",
    },
    "MER": {
        "name": "Mercer", "conference": "SoCon", "tier": "FCS",
        "rank": None, "espn_id": 2382, "color": "#F76800", "alt_color": "#000000",
    },
}

_MOCK_CFB_GAMES = [
    {
        "game_id": "cfb_401752873",
        "week": 1,
        "kickoff": datetime(2026, 9, 5, 23, 30, tzinfo=UTC),
        "home": "OSU",
        "away": "TEX",
        "is_primetime": True,
        "is_divisional": False,
        "home_win_prob": 0.58,
        "venue": {"name": "Ohio Stadium", "city": "Columbus", "is_dome": False},
        "odds": {"spread_home": -3.0, "moneyline_home": -155, "moneyline_away": 130, "total": 51.5},
        "weather": {"temp_f": 78.0, "wind_mph": 5.0, "precipitation": False, "conditions": "Clear"},
        "factors": [
            {"label": "Team rating (Elo) edge", "value": 0.09, "direction": "home"},
            {"label": "AP poll standing edge", "value": 0.06, "direction": "home"},
            {"label": "Betting-market win probability", "value": 0.05, "direction": "home"},
            {"label": "Point differential, last 5 games", "value": -0.03, "direction": "away"},
        ],
        "narrative": (
            "Top-ranked Ohio State gets the nod at 58 percent in the Horseshoe! "
            "The Buckeyes bring a rating edge and the number-one poll standing "
            "against fifth-ranked Texas, and the market leans their way too. "
            "The Longhorns' recent scoring margin keeps them dangerous, but the "
            "model says the home crowd in Columbus tips this heavyweight bout."
        ),
    },
    {
        "game_id": "cfb_401752901",
        "week": 1,
        "kickoff": datetime(2026, 9, 5, 20, 0, tzinfo=UTC),
        "home": "ALA",
        "away": "MER",
        "is_primetime": False,
        "is_divisional": False,
        "home_win_prob": 0.97,
        "venue": {"name": "Bryant-Denny Stadium", "city": "Tuscaloosa", "is_dome": False},
        "odds": None,
        "weather": {"temp_f": 88.0, "wind_mph": 4.0, "precipitation": False, "conditions": "Sunny"},
        "factors": [
            {"label": "FBS-vs-FCS class edge", "value": 0.31, "direction": "home"},
            {"label": "Team rating (Elo) edge", "value": 0.12, "direction": "home"},
            {"label": "AP poll standing edge", "value": 0.04, "direction": "home"},
        ],
        "narrative": (
            "It's fourth-ranked Alabama at a commanding 97 percent over FCS "
            "Mercer in Tuscaloosa! The class edge between divisions does the "
            "heavy lifting, with the Tide's rating advantage piling on. The "
            "Bears would need the upset of the decade to spoil this one."
        ),
    },
    {
        "game_id": "cfb_401753120",
        "week": 2,
        "kickoff": None,
        "home": "TEX",
        "away": "UGA",
        "is_primetime": False,
        "is_divisional": True,
        "home_win_prob": None,
        "venue": {
            "name": "Darrell K Royal-Texas Memorial Stadium",
            "city": "Austin",
            "is_dome": False,
        },
        "odds": None,
        "weather": None,
        "factors": [],
        "narrative": None,
    },
]

MOCK_SEASON = 2026

ESPN_CFB_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png"


def _teams() -> list[dict]:
    return json.loads((SEEDS_DIR / "teams.json").read_text(encoding="utf-8"))


def _team_name(abbr: str) -> str:
    for t in _teams():
        if t["abbr"] == abbr:
            return t["name"]
    return abbr


def _cfb_logo(abbr: str) -> str:
    return ESPN_CFB_LOGO.format(espn_id=_MOCK_CFB_TEAMS[abbr]["espn_id"])


def list_teams(sport: str = SPORT_NFL) -> list[TeamOut]:
    if sport == SPORT_CFB:
        return [
            TeamOut(
                id=i + 1,
                sport=SPORT_CFB,
                abbr=abbr,
                name=t["name"],
                conference=t["conference"],
                division=None,
                logo_url=_cfb_logo(abbr),
                tier=t["tier"],
                color=t["color"],
                alt_color=t["alt_color"],
            )
            for i, (abbr, t) in enumerate(sorted(_MOCK_CFB_TEAMS.items()))
        ]
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


def _game_team(abbr: str, sport: str) -> GameTeam:
    if sport == SPORT_CFB:
        t = _MOCK_CFB_TEAMS[abbr]
        return GameTeam(
            abbr=abbr,
            name=t["name"],
            rank=t["rank"],
            conference=t["conference"],
            logo_url=_cfb_logo(abbr),
            color=t["color"],
        )
    return GameTeam(abbr=abbr, name=nickname(_team_name(abbr)))


def _games_for(sport: str) -> list[dict]:
    return _MOCK_CFB_GAMES if sport == SPORT_CFB else _MOCK_GAMES


def _summary(g: dict, sport: str) -> GameSummary:
    return GameSummary(
        game_id=g["game_id"],
        sport=sport,
        kickoff=g["kickoff"],
        home=_game_team(g["home"], sport),
        away=_game_team(g["away"], sport),
        is_primetime=g["is_primetime"],
        status="scheduled",
        has_prediction=g["home_win_prob"] is not None,
        home_win_prob=g["home_win_prob"],
    )


def get_schedule(season: int, sport: str = SPORT_NFL) -> ScheduleOut:
    games = [g for g in _games_for(sport) if season == MOCK_SEASON]
    weeks: dict[int, list[GameSummary]] = {}
    for g in games:
        weeks.setdefault(g["week"], []).append(_summary(g, sport))
    return ScheduleOut(
        season=season,
        sport=sport,
        weeks=[WeekOut(week=w, games=weeks[w]) for w in sorted(weeks)],
    )


def get_games(season: int, week: int, sport: str = SPORT_NFL) -> list[GameSummary]:
    if season != MOCK_SEASON:
        return []
    return [_summary(g, sport) for g in _games_for(sport) if g["week"] == week]


def _team_detail(abbr: str, sport: str, win_prob: float | None) -> TeamDetail:
    if sport == SPORT_CFB:
        t = _MOCK_CFB_TEAMS[abbr]
        return TeamDetail(
            abbr=abbr,
            name=t["name"],
            record="0-0",
            logo_url=_cfb_logo(abbr),
            win_prob=win_prob,
            rank=t["rank"],
            conference=t["conference"],
            color=t["color"],
        )
    return TeamDetail(
        abbr=abbr,
        name=nickname(_team_name(abbr)),
        record="0-0",
        logo_url=logo_url(abbr),
        win_prob=win_prob,
    )


def get_prediction_detail(game_id: str) -> PredictionOut | None:
    sport = SPORT_CFB if game_id.startswith("cfb_") else SPORT_NFL
    g = next((g for g in _games_for(sport) if g["game_id"] == game_id), None)
    if g is None:
        return None
    prob = g["home_win_prob"]
    version = "cfb-0.1.0-mock" if sport == SPORT_CFB else "0.1.0-mock"
    return PredictionOut(
        game_id=g["game_id"],
        sport=sport,
        season=MOCK_SEASON,
        week=g["week"],
        kickoff=g["kickoff"],
        venue=VenueOut(**g["venue"]),
        is_primetime=g["is_primetime"],
        is_divisional=g["is_divisional"],
        home=_team_detail(g["home"], sport, prob),
        away=_team_detail(g["away"], sport, None if prob is None else round(1 - prob, 4)),
        odds=OddsOut(**g["odds"]) if g["odds"] else None,
        weather=WeatherOut(**g["weather"]) if g["weather"] else None,
        factors=[FactorOut(**f) for f in g["factors"]],
        narrative=g["narrative"],
        model_version=version if prob is not None else None,
        predicted_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC) if prob is not None else None,
        prediction_status="available" if prob is not None else "pending",
    )
