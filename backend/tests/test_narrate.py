"""Narration tests -- the real Anthropic API is never called."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import narrate as narrate_mod

PAYLOAD = {
    "home_name": "Kansas City Chiefs",
    "home_abbr": "KC",
    "away_name": "Buffalo Bills",
    "away_abbr": "BUF",
    "home_win_prob": 0.63,
    "factors": [
        {"label": "Team rating (Elo) edge", "value": 0.14, "direction": "home"},
    ],
    "spread_home": -2.5,
}


@pytest.fixture()
def settings_with_key(monkeypatch):
    settings = narrate_mod.get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    return settings


def _mock_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(narrate_mod.get_settings(), "anthropic_api_key", "")
    assert narrate_mod.narrate(PAYLOAD) is None


def test_successful_narration(settings_with_key):
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "The Chiefs carry a 63% edge behind their rating advantage!"
    )
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        result = narrate_mod.narrate(PAYLOAD)
    assert result is not None
    assert "63%" in result
    client.messages.create.assert_called_once()


def test_api_error_falls_back_to_none(settings_with_key, monkeypatch):
    monkeypatch.setattr(narrate_mod.time, "sleep", lambda _: None)
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("api down")
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(PAYLOAD) is None
    assert client.messages.create.call_count == 2  # one retry with backoff


def test_wrong_percentage_rejected(settings_with_key, monkeypatch):
    monkeypatch.setattr(narrate_mod.time, "sleep", lambda _: None)
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "Kansas City wins this 90% of the time!"
    )
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(PAYLOAD) is None


def test_away_percentage_accepted(settings_with_key):
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "Buffalo hangs around with a 37 percent shot at the upset."
    )
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(PAYLOAD) is not None


def test_percentage_sanity_helper():
    assert narrate_mod._percentages_consistent("a 63% chance", 0.63)
    assert narrate_mod._percentages_consistent("37 percent underdogs", 0.63)
    assert not narrate_mod._percentages_consistent("an 80% lock", 0.63)
    assert narrate_mod._percentages_consistent("no numbers here", 0.63)
