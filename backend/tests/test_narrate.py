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


def test_favorite_attribution_rejects_underdog_called_favorite():
    """Real bug found in production: the model correctly cites the right
    percentage but calls the underdog the favorite (cfb_401856677,
    MSST @ MINN, home_win_prob=0.556 -- MINN is the actual favorite)."""
    payload = {
        **PAYLOAD,
        "home_name": "Minnesota",
        "home_abbr": "MINN",
        "away_name": "Mississippi State",
        "away_abbr": "MSST",
        "home_win_prob": 0.556,
    }
    text = (
        "Mississippi State comes in as a slight favorite on the road here, "
        "but Minnesota's got this thing pretty close to a coin flip at 56 "
        "percent to win."
    )
    assert not narrate_mod._favorite_attribution_consistent(text, payload)


def test_favorite_attribution_accepts_correct_call():
    payload = {**PAYLOAD, "home_win_prob": 0.556}
    text = (
        "Kansas City comes in as a slight favorite here at 56 percent, but "
        "Buffalo can absolutely make this a coin flip."
    )
    assert narrate_mod._favorite_attribution_consistent(text, payload)


def test_favorite_attribution_ignores_text_with_no_favorite_language():
    assert narrate_mod._favorite_attribution_consistent(
        "Buffalo hangs around with a 37 percent shot at the upset.", PAYLOAD
    )


def test_market_attribution_rejects_wrong_team_favored_by_vegas():
    """Real bug found live, post-fix: the model favors the away team
    overall (so 'X favored' passes the general favorite check), but the
    same narrative separately claims Vegas favors that same team when the
    raw spread actually favors home (cfb_401856682, OSU@TEX: spread_home
    =+1.5 favors home/Texas, but narration said 'Vegas has Ohio State
    favored by a point and a half')."""
    payload = {
        **PAYLOAD,
        "home_name": "Texas",
        "home_abbr": "TEX",
        "away_name": "Ohio State",
        "away_abbr": "OSU",
        "home_win_prob": 0.452,
        "spread_home": 1.5,
    }
    text = (
        "Ohio State comes in with the edge here at 55 percent. The Vegas "
        "line has Ohio State favored by a point and a half, and that's "
        "where the smart money is."
    )
    assert not narrate_mod._market_attribution_consistent(text, payload)


def test_market_attribution_accepts_correct_call():
    payload = {
        **PAYLOAD,
        "home_name": "Texas",
        "home_abbr": "TEX",
        "away_name": "Ohio State",
        "away_abbr": "OSU",
        "home_win_prob": 0.452,
        "spread_home": 1.5,
    }
    text = "The Vegas line has Texas favored by a point and a half at home."
    assert narrate_mod._market_attribution_consistent(text, payload)


def test_market_attribution_skipped_without_a_spread():
    payload = {**PAYLOAD, "spread_home": None}
    text = "The Vegas line has Buffalo favored here."
    assert narrate_mod._market_attribution_consistent(text, payload)


def test_market_attribution_ignores_non_market_sentences():
    """The model is allowed to disagree with the market -- only sentences
    that actually reference the market are checked."""
    payload = {
        **PAYLOAD,
        "home_name": "Texas",
        "home_abbr": "TEX",
        "away_name": "Ohio State",
        "away_abbr": "OSU",
        "home_win_prob": 0.452,
        "spread_home": 1.5,
    }
    text = "Ohio State is the model's pick here at 55 percent."
    assert narrate_mod._market_attribution_consistent(text, payload)


def test_wrong_favorite_rejected_end_to_end(settings_with_key, monkeypatch):
    monkeypatch.setattr(narrate_mod.time, "sleep", lambda _: None)
    payload = {**PAYLOAD, "home_win_prob": 0.556}
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "Buffalo comes in as a slight favorite here, sitting at 56 percent."
    )
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(payload) is None


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
