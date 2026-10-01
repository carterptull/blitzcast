"""Neutral-site games (no Team-derived stadium) must not be silently
skipped the same way domes are — they should be fetched by venue name."""
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import SPORT_NFL, Game, Weather
from data_pipeline import refresh_weather
from data_pipeline.refresh_weather import exit_code, fetch_day, select_games


def test_fetch_day_accepts_lat_lon_string():
    with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"days": []}
        mock_get.return_value.raise_for_status.return_value = None
        fetch_day("33.9535,-118.3392", "2026-09-10", "key")
        url = mock_get.call_args[0][0]
        assert "33.9535,-118.3392" in url


def test_fetch_day_accepts_venue_name_string():
    with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"days": []}
        mock_get.return_value.raise_for_status.return_value = None
        fetch_day("Melbourne Cricket Ground", "2026-09-10", "key")
        url = mock_get.call_args[0][0]
        assert "Melbourne Cricket Ground" in url


def _game(db, game_id, kickoff, home_id, away_id):
    db.add(Game(
        game_id=game_id, sport=SPORT_NFL, season=2026, week=3,
        game_date=kickoff.date(), kickoff_time=kickoff,
        home_team_id=home_id, away_team_id=away_id, status="scheduled",
    ))
    db.flush()


def test_backfill_picks_up_past_games_missing_weather(db):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    _game(db, "2026_03_BUF_KC", now - timedelta(days=4), 1, 2)
    _game(db, "2026_03_DAL_PHI", now - timedelta(days=4), 3, 4)
    db.add(Weather(game_id="2026_03_DAL_PHI", temp_f=70.0, captured_at=now))
    db.flush()

    ids = {g.game_id for g in select_games(db, SPORT_NFL, now, days=8, backfill_days=7)}
    assert "2026_03_BUF_KC" in ids
    assert "2026_03_DAL_PHI" not in ids  # already has weather


def test_no_backfill_keeps_the_forward_window_only(db):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    _game(db, "2026_03_BUF_KC", now - timedelta(days=4), 1, 2)
    ids = {g.game_id for g in select_games(db, SPORT_NFL, now, days=8, backfill_days=0)}
    assert "2026_03_BUF_KC" not in ids


def test_exit_code_fails_only_when_every_call_failed():
    assert exit_code(updated=0, failed=0) == 0
    assert exit_code(updated=5, failed=2) == 0
    assert exit_code(updated=0, failed=3) == 1


def test_missing_key_warns_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(refresh_weather.get_settings(), "visual_crossing_api_key", "")
    monkeypatch.setattr(sys, "argv", ["refresh_weather", "--sport", "cfb"])
    with pytest.raises(SystemExit) as exc:
        refresh_weather.main()
    assert exc.value.code == 0
    assert "WARNING" in capsys.readouterr().out
