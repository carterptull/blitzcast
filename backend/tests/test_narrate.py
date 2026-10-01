"""Narration tests: the real Anthropic API is never called."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import narrate as narrate_mod
from app.services.fact_sheet import GameFacts, TeamFacts
from app.services.narrate import check_narration


def _team(name, full, abbr, mascot, record="2-1"):
    return TeamFacts(
        name=name, full_name=full, abbr=abbr, mascot=mascot, record=record,
        games_this_season=3, last_game=None, streak=None, scoring=None,
        rank=None, rank_note=None, rest=None, injuries=(),
    )


TEX = _team("Texas", "Texas Longhorns", "TEX", "Longhorns")
OSU = _team("Ohio State", "Ohio State Buckeyes", "OSU", "Buckeyes")
# The real OSU @ TEX bug: model favored OSU 55%, market favored Texas by 1.5.
FACTS = GameFacts(
    sport="CFB", home=TEX, away=OSU, home_win_prob=0.45, spread_home=1.5, total=49.5,
    when="Saturday night", venue="DKR-Texas Memorial Stadium in Austin",
    is_neutral_site=False, matchup_note="nonconference game, Big Ten at SEC",
    last_meeting=None, weather="97 degrees, wind 12 mph", factor_lines=("Texas: betting market",),
)
GOOD = (
    "A top-five heavyweight fight in Austin on Saturday night. Our model leans Ohio State "
    "at 55% on the road, even with Texas favored by 1.5 in the betting market."
)


@pytest.fixture()
def settings_with_key(monkeypatch):
    settings = narrate_mod.get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(narrate_mod.time, "sleep", lambda _: None)
    return settings


def _mock_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_good_narration_passes():
    assert check_narration(GOOD, FACTS) is None


@pytest.mark.parametrize("text, reason_fragment", [
    ("Vegas has Ohio State getting the nod by 1.5 in this one.", "betting favorite"),
    ("Texas is getting 1.5 points at home, our model likes Ohio State at 55%.", "getting points"),
    ("Vegas makes Texas a 3 point favorite. Ohio State 55%.", "line is 1.5"),
    ("Ohio State sits at fifty-five percent to win.", "digits"),
    ("Ohio State is at 70% to win.", "percentage"),
    ("Arch Manning and the Longhorns host Ohio State, 55% for them.", "not in the fact sheet"),
    ("Folks, Ohio State at 55% is the call.", "banned"),
    ("Texas is the favorite here at 45%.", "model's favorite"),
])
def test_rejections(text, reason_fragment):
    reason = check_narration(text, FACTS)
    assert reason is not None and reason_fragment in reason


def test_mascots_count_as_team_mentions():
    text = "The Buckeyes are getting 1.5 points in Austin, and our model still likes them at 55%."
    assert check_narration(text, FACTS) is None


def test_market_talk_is_rejected_when_no_line_exists():
    facts = replace(FACTS, spread_home=None, total=None, factor_lines=())
    reason = check_narration("Vegas likes Ohio State here, 55% for the Buckeyes.", facts)
    assert reason is not None and "no line" in reason


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(narrate_mod.get_settings(), "anthropic_api_key", "")
    assert narrate_mod.narrate(FACTS) is None


def test_retry_feeds_back_the_rejection_reason(settings_with_key):
    client = MagicMock()
    client.messages.create.side_effect = [
        _mock_response("Ohio State is at 70% to win."),
        _mock_response(GOOD),
    ]
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        result = narrate_mod.generate(FACTS)
    assert result.text == GOOD
    assert result.attempts == 2
    second_messages = client.messages.create.call_args_list[1].kwargs["messages"]
    assert "percentage" in second_messages[-1]["content"]


def test_all_attempts_rejected_returns_none(settings_with_key):
    client = MagicMock()
    client.messages.create.return_value = _mock_response("Ohio State is at 70% to win.")
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(FACTS) is None
    assert client.messages.create.call_count == narrate_mod.MAX_ATTEMPTS


def test_api_error_falls_back_to_none(settings_with_key):
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("api down")
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        assert narrate_mod.narrate(FACTS) is None


def test_cfb_prompt_carries_injury_guardrail():
    assert "injury" in narrate_mod._system_prompt("CFB").lower()


def test_dashes_are_rewritten():
    assert "—" not in narrate_mod._plain_punctuation("Texas — at home — rolls.")
