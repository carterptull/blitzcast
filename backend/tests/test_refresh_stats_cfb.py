"""CFB in-season stats refresh: skips cleanly with no key or no finals."""
import sys
from unittest.mock import patch

import pytest

from app.models import Game
from data_pipeline import refresh_stats_cfb


def test_has_final_games_requires_both_scores(db):
    assert refresh_stats_cfb.has_final_games(db, 2026) is False
    game = db.get(Game, "cfb_401800001")
    game.home_score = 21
    db.flush()
    assert refresh_stats_cfb.has_final_games(db, 2026) is False  # half-scored
    game.away_score = 14
    db.flush()
    assert refresh_stats_cfb.has_final_games(db, 2026) is True


def test_missing_key_warns_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(refresh_stats_cfb.get_settings(), "cfbd_api_key", "")
    monkeypatch.setattr(sys, "argv", ["refresh_stats_cfb"])
    with pytest.raises(SystemExit) as exc:
        refresh_stats_cfb.main()
    assert exc.value.code == 0
    assert "WARNING" in capsys.readouterr().out


def test_cfbd_failure_exits_one(monkeypatch, db):
    import requests

    monkeypatch.setattr(refresh_stats_cfb.get_settings(), "cfbd_api_key", "k")
    monkeypatch.setattr(sys, "argv", ["refresh_stats_cfb"])
    monkeypatch.setattr(refresh_stats_cfb, "has_final_games", lambda *_: True)
    with patch.object(
        refresh_stats_cfb, "backfill_team_game_stats",
        side_effect=requests.RequestException("boom"),
    ), patch.object(refresh_stats_cfb, "session_scope") as scope:
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False  # don't swallow SystemExit
        with pytest.raises(SystemExit) as exc:
            refresh_stats_cfb.main()
    assert exc.value.code == 1
