"""NFL schedule loader tests: nflverse's whole-week placeholder gametime
must not be presented as a confirmed kickoff."""

import pandas as pd

from app.models import SPORT_NFL, Game
from data_pipeline.games_loader import _kickoff_utc, upsert_games


def _row(game_id, season, week, gameday, gametime, home="KC", away="BUF"):
    return {
        "game_id": game_id, "season": season, "week": week, "gameday": gameday,
        "gametime": gametime, "home_team": home, "away_team": away, "location": "Home",
        "home_score": None, "away_score": None, "div_game": False,
        "spread_line": None, "total_line": None, "home_moneyline": None, "away_moneyline": None,
    }


def test_week_with_uniform_gametime_treated_as_tbd(db):
    """A week where every game shares one gametime is nflverse's not-yet-scheduled
    placeholder, not a real simultaneous kickoff — must not be presented as confirmed."""
    schedules = pd.DataFrame([
        _row("2026_18_A", 2026, 18, "2027-01-10", "13:00", "KC", "BUF"),
        _row("2026_18_B", 2026, 18, "2027-01-10", "13:00", "PHI", "DAL"),
        _row("2026_18_C", 2026, 18, "2027-01-10", "13:00", "DAL", "KC"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 18
        )
    }
    assert len(games) == 3
    assert all(g.kickoff_time is None for g in games.values())
    assert all(g.is_primetime is False for g in games.values())


def test_week_with_varied_gametimes_kept_as_real(db):
    """A week with genuinely distinct kickoff times must not be flagged as a placeholder."""
    schedules = pd.DataFrame([
        _row("2026_03_A", 2026, 3, "2026-09-24", "13:00", "KC", "BUF"),
        _row("2026_03_B", 2026, 3, "2026-09-24", "16:25", "PHI", "DAL"),
        _row("2026_03_C", 2026, 3, "2026-09-24", "20:20", "DAL", "KC"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 3
        )
    }
    assert len(games) == 3
    assert all(g.kickoff_time is not None for g in games.values())


def test_two_games_sharing_a_time_not_flagged_as_placeholder(db):
    """Threshold is more than 2 games — a bye-heavy week with only two games
    sharing a time by coincidence must not be treated as TBD."""
    schedules = pd.DataFrame([
        _row("2026_17_A", 2026, 17, "2027-01-03", "13:00", "KC", "BUF"),
        _row("2026_17_B", 2026, 17, "2027-01-03", "13:00", "PHI", "DAL"),
    ])
    upsert_games(db, schedules)
    games = {
        g.game_id: g for g in db.query(Game).filter(
            Game.sport == SPORT_NFL, Game.season == 2026, Game.week == 17
        )
    }
    assert len(games) == 2
    assert all(g.kickoff_time is not None for g in games.values())


def test_kickoff_utc_returns_none_for_missing_gametime():
    """A single row with no gametime at all is a narrower, per-row unknown —
    must not default to a fake 13:00 kickoff either."""
    assert _kickoff_utc("2026-09-17", None) is None


def test_kickoff_utc_computes_real_time_when_known():
    kickoff = _kickoff_utc("2026-09-17", "16:25")
    assert kickoff is not None
