"""predict_week selection predicates and narration payload shaping."""

from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import select

from app.jobs.predict_week import build_narration_payload, default_week
from app.models import SPORT_CFB, SPORT_NFL, Game, Team


def test_default_week_is_sport_scoped(db):
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    assert default_week(db, 2026, SPORT_NFL, now=now) == 1
    assert default_week(db, 2026, SPORT_CFB, now=now) == 1
    assert default_week(db, 2025, SPORT_NFL, now=now) is None  # all played
    assert default_week(db, 2025, SPORT_CFB, now=now) is None  # no CFB games that season


def test_null_kickoff_game_still_selected(db):
    """A scheduled game with a TBD (NULL) kickoff must not drop out of the
    target-week selection."""
    uga = db.query(Team).filter_by(sport=SPORT_CFB, abbr="UGA").one()
    mer = db.query(Team).filter_by(sport=SPORT_CFB, abbr="MER").one()
    db.add(
        Game(
            game_id="cfb_401900001",
            sport=SPORT_CFB, season=2027, week=5,
            game_date=date(2027, 10, 2), kickoff_time=None,
            home_team_id=uga.team_id, away_team_id=mer.team_id,
            status="scheduled",
        )
    )
    db.flush()
    now = datetime(2027, 10, 2, 12, 0, tzinfo=UTC)
    assert default_week(db, 2027, SPORT_CFB, now=now) == 5


def _team(sport: str, abbr: str, name: str, conference: str, team_id: int) -> Team:
    team = Team(sport=sport, abbr=abbr, name=name, conference=conference)
    team.team_id = team_id
    return team


def test_cfb_payload_has_color_keys_and_no_injury_keys():
    teams = {
        "ALA": _team(SPORT_CFB, "ALA", "Alabama", "SEC", 1),
        "UGA": _team(SPORT_CFB, "UGA", "Georgia", "SEC", 2),
    }
    row = pd.Series(
        {
            "home_abbr": "ALA", "away_abbr": "UGA",
            "market_spread_home": -1.5, "is_divisional": 1.0,
        }
    )
    payload = build_narration_payload(
        row, 0.55, [], teams, SPORT_CFB, ranks={1: 7, 2: 3}
    )
    assert payload["sport"] == "CFB"
    assert "ranked #7" in payload["poll_note"]
    assert "ranked #3" in payload["poll_note"]
    assert payload["conference_note"] == "Same-conference clash in the SEC"
    assert "qb_note" not in payload
    assert not any("injury" in k for k in payload)


def test_cfb_payload_omits_poll_note_when_unranked():
    teams = {
        "UGA": _team(SPORT_CFB, "UGA", "Georgia", "SEC", 1),
        "MER": _team(SPORT_CFB, "MER", "Mercer", "SoCon", 2),
    }
    row = pd.Series(
        {
            "home_abbr": "UGA", "away_abbr": "MER",
            "market_spread_home": None, "is_divisional": 0.0,
        }
    )
    payload = build_narration_payload(row, 0.97, [], teams, SPORT_CFB, ranks={})
    assert "poll_note" not in payload
    assert "conference_note" not in payload
    assert payload["spread_home"] is None


def test_nfl_payload_shape_unchanged():
    teams = {
        "KC": _team(SPORT_NFL, "KC", "Kansas City Chiefs", "AFC", 1),
        "BUF": _team(SPORT_NFL, "BUF", "Buffalo Bills", "AFC", 2),
    }
    row = pd.Series(
        {
            "home_abbr": "KC", "away_abbr": "BUF",
            "market_spread_home": -2.5, "is_divisional": 0.0,
        }
    )
    factors = [{"label": "Team rating (Elo) edge", "value": 0.14, "direction": "home"}]
    payload = build_narration_payload(row, 0.63, factors, teams, SPORT_NFL, ranks={1: 5})
    assert set(payload) == {
        "sport", "home_name", "home_abbr", "away_name", "away_abbr",
        "home_win_prob", "factors", "spread_home",
    }
    assert payload["home_name"] == "Kansas City Chiefs"
    assert payload["spread_home"] == -2.5


def test_unplayed_game_ids_excludes_finished_games(db):
    """A finished game must not be re-predicted; that would overwrite the
    pre-game call and restamp predicted_at after the result was known."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    week = game.week
    assert "2026_01_BUF_KC" in unplayed_game_ids(db, 2026, week, SPORT_NFL)

    game.home_score, game.away_score = 27, 24
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(db, 2026, week, SPORT_NFL)


def test_unplayed_game_ids_excludes_a_half_scored_row(db):
    """One score present means the game started; do not predict it."""
    from app.jobs.predict_week import unplayed_game_ids

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    game.home_score, game.away_score = 27, None
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(db, 2026, game.week, SPORT_NFL)


def test_default_week_skips_a_stale_week_with_a_permanently_unscored_game(db):
    """A cancelled week 1 game must not pin default_week to week 1 forever."""
    wk1 = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    wk1.home_score = None          # never resolved
    wk1.away_score = None
    wk1.kickoff_time = datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
    db.commit()

    now = datetime(2026, 10, 1, tzinfo=UTC)   # weeks later
    assert default_week(db, 2026, SPORT_NFL, now=now) != 1
