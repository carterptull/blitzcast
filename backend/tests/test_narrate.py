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


CFB_PAYLOAD = {
    "sport": "CFB",
    "home_name": "Alabama",
    "home_abbr": "ALA",
    "away_name": "Georgia",
    "away_abbr": "UGA",
    "home_win_prob": 0.55,
    "factors": [
        {"label": "AP poll standing edge", "value": 0.08, "direction": "home"},
    ],
    "spread_home": -1.5,
    "poll_note": "Alabama ranked #7, Georgia ranked #3 (AP poll entering the week)",
    "conference_note": "Same-conference clash in the SEC",
}


def test_cfb_system_prompt_has_injury_guardrail(settings_with_key):
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "Alabama takes it 55 percent of the time in this SEC slugfest!"
    )
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(CFB_PAYLOAD) is not None
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == narrate_mod.SYSTEM_PROMPT + " " + narrate_mod.CFB_INJURY_GUARDRAIL
    assert "injury" in kwargs["system"]
    content = kwargs["messages"][0]["content"]
    assert "Poll standing" in content
    assert "Conference matchup" in content
    assert "QB status" not in content


def test_nfl_system_prompt_unchanged(settings_with_key):
    client = MagicMock()
    client.messages.create.return_value = _mock_response("Chiefs at 63%!")
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        narrate_mod.narrate(PAYLOAD)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == narrate_mod.SYSTEM_PROMPT
    assert narrate_mod.CFB_INJURY_GUARDRAIL not in kwargs["system"]


def test_cfb_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(narrate_mod.get_settings(), "anthropic_api_key", "")
    assert narrate_mod.narrate(CFB_PAYLOAD) is None
