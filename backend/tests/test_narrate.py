"""Narration tests: the real Anthropic API is never called."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from app.services import narrate as narrate_mod
from app.services.fact_sheet import GameFacts, TeamFacts, render_fact_sheet
from app.services.narrate import check_narration


def _team(name, full, abbr, mascot, record="2-1", **kw):
    base = dict(
        name=name, full_name=full, abbr=abbr, mascot=mascot, record=record,
        games_this_season=3, last_game=None, streak=None, scoring=None,
        rank=None, rank_note=None, rest=None, injuries=(),
    )
    return TeamFacts(**(base | kw))


def _facts(home, away, p, spread, total=None, sport="CFB", **kw):
    base = dict(
        sport=sport, home=home, away=away, home_win_prob=p, spread_home=spread, total=total,
        when="Saturday night", venue=None, is_neutral_site=False, matchup_note=None,
        last_meeting=None, weather=None, factor_lines=(),
    )
    return GameFacts(**(base | kw))


TEX = _team(
    "Texas", "Texas Longhorns", "TEX", "Longhorns", last_game="beat Baylor 38-17 at home"
)
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

MSU = _team("Michigan State", "Michigan State Spartans", "MSU", "Spartans")
OSU_HOME = _team("Ohio State", "Ohio State Buckeyes", "OSU", "Buckeyes")
# Ohio State hosts and is favored by 3.5; the model has Ohio State 62%.
MSU_AT_OSU = _facts(OSU_HOME, MSU, 0.62, 3.5, venue="Ohio Stadium in Columbus")

KU = _team("Kansas", "Kansas Jayhawks", "KU", "Jayhawks")
KSU = _team("Kansas State", "Kansas State Wildcats", "KSU", "Wildcats")
# Kansas State hosts and is favored by 2.5; the model has Kansas State 58%.
KU_AT_KSU = _facts(KSU, KU, 0.58, 2.5)

ARK = _team("Arkansas", "Arkansas Razorbacks", "ARK", "Razorbacks")
KU_HOME = _team("Kansas", "Kansas Jayhawks", "KU", "Jayhawks")
ARK_AT_KU = _facts(KU_HOME, ARK, 0.40, -2.5)

LAR = _team("Rams", "Los Angeles Rams", "LA", "Rams")
LAC = _team("Chargers", "Los Angeles Chargers", "LAC", "Chargers")
# Chargers host, favored by 2.5; the model has the Chargers 58%.
RAMS_AT_LAC = _facts(LAC, LAR, 0.58, 2.5, sport="NFL")

PIT = _team(
    "Steelers", "Pittsburgh Steelers", "PIT", "Steelers",
    last_game="beat the Bengals 30-27 at home", rest="on a short week",
)
CLE = _team(
    "Browns", "Cleveland Browns", "CLE", "Browns",
    last_game="beat the Panthers 21-18 on the road", streak="won 2 straight",
    injuries=("Deshaun Watson (QB) is listed Out",),
)
NFL_FACTS = _facts(
    CLE, PIT, 0.38, -2.5, total=38.5, sport="NFL", when="Thursday night",
    matchup_note="AFC North division game", last_meeting="Browns won 13-6 in Week 17 of 2025",
)


@pytest.fixture()
def settings_with_key(monkeypatch):
    settings = narrate_mod.get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    sleeps = []
    monkeypatch.setattr(narrate_mod.time, "sleep", sleeps.append)
    return sleeps


def _mock_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_good_narration_passes():
    assert check_narration(GOOD, FACTS) is None


ACCEPT = [
    (GOOD, FACTS),
    ("The Buckeyes are getting 1.5 points in Austin, and our model still likes them at 55%.",
     FACTS),
    # Model / market disagreement inside one sentence (Important 7).
    ("Texas is a 1.5-point favorite at home, but our model likes Ohio State at 55%.", FACTS),
    ("Vegas likes Texas by 1.5, but our model likes Ohio State at 55%.", FACTS),
    # Stadium name containing a team name (Critical 2).
    ("Ohio State walks into DKR-Texas Memorial Stadium as the model's favorite at 55%.", FACTS),
    # Percentages tied to the right team (Critical 1).
    ("It is 55% for the Buckeyes in our model.", FACTS),
    ("Texas hosts, but Ohio State is the 55% side.", FACTS),
    ("The Longhorns are at 45% at home.", FACTS),
    ("Ohio State sits at 55%, while the Longhorns are at 45%.", FACTS),
    ("The model sides with Ohio State, 55% to 45%.", FACTS),
    # Openers and capitalized plain words (Important 5).
    ("Forget the heat in Austin. Primetime football on Saturday Night, and our model leans "
     "Ohio State at 55%.", FACTS),
    ("Tonight in Austin, Texas hosts Ohio State. Yet our model likes the visitors at 55%.",
     FACTS),
    ("Make no mistake, this is a heavyweight fight. Neither team blinks, and our model gives "
     "Ohio State the edge at 55%.", FACTS),
    ("Plus the Buckeyes bring a 2-1 record into Austin. Call it a road test, and our model "
     "still has Ohio State at 55%.", FACTS),
    ("Heavyweight fight in Austin. Coming off a bye or not, our model likes Ohio State at 55%.",
     FACTS),
    # Possessives ending in s, straight and curly apostrophes.
    ("The Longhorns' defense meets the Buckeyes' offense, and Texas' crowd will be loud. "
     "Our model still likes Ohio State at 55%.", FACTS),
    ("Texas’ home crowd waits, but our model likes Ohio State at 55%.", FACTS),
    # Market wording with the right team and number (Important 3 and 4).
    ("Texas is laying 1.5 at home.", FACTS),
    ("Ohio State is getting 1.5 points on the road.", FACTS),
    ("Texas -1.5 at home, Ohio State +1.5, and our model leans the Buckeyes at 55%.", FACTS),
    ("The line is 1.5 for Texas with a total of 49.5.", FACTS),
    # A score margin inside a market sentence is not the line (minor 11).
    ("Texas beat Baylor by 21 points last time out, and Vegas has the Longhorns favored by 1.5.",
     FACTS),
    # Conference names and abbreviation-aware sentence splitting (minor 12).
    ("Ohio State vs. Texas is the game of the week. Forget the records. Big Ten at SEC in "
     "Austin. Our model likes Ohio State at 55%.", FACTS),
    # Shared-name teams (Critical 2).
    ("Ohio State is favored by 3.5 at home, and our model gives Michigan State 38%.",
     MSU_AT_OSU),
    ("Michigan State is getting 3.5 on the road in Columbus.", MSU_AT_OSU),
    ("Kansas State is the 58% side at home, and Kansas is getting 2.5.", KU_AT_KSU),
    ("The Wildcats are favored by 2.5 over Kansas.", KU_AT_KSU),
    ("Arkansas is the favorite at 60% over Kansas.", ARK_AT_KU),
    ("The Chargers host the Rams as 2.5-point favorites, and our model has them at 58%.",
     RAMS_AT_LAC),
    # Scores, records, streaks, Week N of season, injury names (NFL).
    ("The Browns won 13-6 in Week 17 of 2025 and have won 2 straight. Pittsburgh is 2-1 after "
     "beating the Bengals 30-27 at home, and our model likes the Steelers at 62%.", NFL_FACTS),
    ("Cleveland is without Deshaun Watson, who is listed out, and our model likes the Steelers "
     "at 62%.", NFL_FACTS),
    ("The AFC North gets a Thursday night fight with a total of 38.5, and the Steelers are "
     "laying 2.5 on the road.", NFL_FACTS),
]


@pytest.mark.parametrize("text, facts", ACCEPT)
def test_accepts_good_copy(text, facts):
    assert check_narration(text, facts) is None


REJECT = [
    # Original production failures.
    ("Vegas has Ohio State getting the nod by 1.5 in this one.", FACTS, "betting favorite"),
    ("Texas is getting 1.5 points at home, our model likes Ohio State at 55%.", FACTS,
     "getting points"),
    ("Vegas makes Texas a 3 point favorite. Ohio State 55%.", FACTS, "line is 1.5"),
    ("Ohio State sits at fifty-five percent to win.", FACTS, "digits"),
    ("Ohio State is at 70% to win.", FACTS, "percentage"),
    ("Arch Manning and the Longhorns host Ohio State, 55% for them.", FACTS,
     "not in the fact sheet"),
    ("Folks, Ohio State at 55% is the call.", FACTS, "banned"),
    ("Texas is the favorite here at 45%.", FACTS, "model's favorite"),
    # Critical 1: a percentage on the wrong team.
    ("Our model likes Texas at 55% in this one.", FACTS, "the model has Texas at 45%"),
    ("Texas is at 55% to win at home.", FACTS, "the model has Texas at 45%"),
    ("The Longhorns sit at 55% at home.", FACTS, "the model has Texas at 45%"),
    # Critical 2: shared-name teams.
    ("Michigan State is favored by 3.5 on the road.", MSU_AT_OSU, "betting favorite"),
    ("Michigan State is the model's favorite at 62%.", MSU_AT_OSU,
     "the model has Michigan State at 38%"),
    ("Kansas is favored by 2.5 on the road.", KU_AT_KSU, "betting favorite"),
    ("Our model likes Kansas at 58%.", KU_AT_KSU, "the model has Kansas at 42%"),
    ("Kansas is the favorite at 60% at home.", ARK_AT_KU, "the model has Kansas at 40%"),
    ("The Rams visit the Chargers as 2.5-point favorites.", RAMS_AT_LAC, "betting favorite"),
    ("Los Angeles Rams are favored by 2.5 on the road.", RAMS_AT_LAC, "betting favorite"),
    # Important 3 and 4: market wording.
    ("Vegas has Ohio State at minus 1.5.", FACTS, "betting favorite"),
    ("The line has Ohio State -1.5.", FACTS, "betting favorite"),
    ("Ohio State is giving 1.5 on the road.", FACTS, "betting favorite"),
    ("Texas sits at plus 1.5 at home per the line.", FACTS, "getting points"),
    ("Vegas has Ohio State favored by 7.", FACTS, "betting favorite"),
    ("Ohio State is a 7-point favorite.", FACTS, "betting favorite"),
    ("Texas is favored by 7 at home.", FACTS, "line is 1.5"),
    ("Texas is a 7-point favorite at home.", FACTS, "line is 1.5"),
    ("Texas is the underdog in the betting market.", FACTS, "underdog"),
    ("Vegas likes the Buckeyes in this one.", FACTS, "betting favorite"),
    ("The total sits at 55.5 with Texas favored by 1.5.", FACTS, "total is 49.5"),
    # Minor 8: spelled-out numbers.
    ("Texas is getting a point and a half.", FACTS, "digits"),
    ("Texas is favored by three and a half.", FACTS, "digits"),
    ("Ohio State rides a five game streak into Austin.", FACTS, "digits"),
    ("Ohio State checks in at 98 per cent.", FACTS, "percentage"),
    # Minor 9: CFB injuries.
    ("Texas is missing two starters, so our model likes Ohio State at 55%.", FACTS, "injur"),
    ("Ohio State has a quarterback listed questionable.", FACTS, "injur"),
    ("Texas lost a starter to injury last week.", FACTS, "injur"),
    # Minor 10: an injury-report name on the wrong team.
    ("The Steelers will be without Deshaun Watson.", NFL_FACTS, "Deshaun Watson"),
    # Minor 12: abbreviations do not hide a fifth sentence.
    ("Ohio State vs. Texas is the game. No. 1 storyline is heat. Big Ten at SEC. Forget the "
     "records. Our model likes Ohio State at 55%.", FACTS, "more than 4 sentences"),
]


@pytest.mark.parametrize("text, facts, reason_fragment", REJECT)
def test_rejections(text, facts, reason_fragment):
    reason = check_narration(text, facts)
    assert reason is not None and reason_fragment in reason, reason


@pytest.mark.parametrize("name", [
    "Arch Manning", "Mahomes", "Rodgers", "T.J. Watt", "Allen", "Love", "Brown", "Sarkisian",
    "Dallas", "Columbus",
])
def test_invented_names_stay_rejected(name):
    reason = check_narration(f"Ohio State is at 55% with {name} in the building.", FACTS)
    assert reason is not None and "not in the fact sheet" in reason


def test_mascots_count_as_team_mentions():
    text = "The Buckeyes are getting 1.5 points in Austin, and our model still likes them at 55%."
    assert check_narration(text, FACTS) is None


def test_market_talk_is_rejected_when_no_line_exists():
    facts = replace(FACTS, spread_home=None, total=None, factor_lines=())
    for text in (
        "Vegas likes Ohio State here, 55% for the Buckeyes.",
        "Ohio State is a 3-point favorite on the road.",
    ):
        reason = check_narration(text, facts)
        assert reason is not None and "no line" in reason


def test_pickem_has_no_betting_favorite():
    facts = replace(FACTS, spread_home=0.0, factor_lines=())
    assert check_narration(
        "Vegas calls it a pick'em, but our model likes Ohio State at 55%.", facts
    ) is None
    reason = check_narration("Vegas has Texas favored at home.", facts)
    assert reason is not None and "pick'em" in reason


def test_one_as_a_pronoun_is_not_a_spelled_number():
    text = "One of the best defenses in the country visits Austin, and our model likes Ohio State "
    assert check_narration(text + "at 55%.", FACTS) is None


def _example_facts():
    return _facts(
        _team(
            "Browns", "Cleveland Browns", "CLE", "Browns",
            last_game="beat the Panthers 21-18 on the road", streak="won 2 straight",
        ),
        _team(
            "Steelers", "Pittsburgh Steelers", "PIT", "Steelers",
            last_game="beat the Bengals 30-27 at home", rest="on a short week",
        ),
        0.38, -2.5, total=38.5, sport="NFL", when="Thursday night",
        matchup_note="AFC North division game",
        last_meeting="Browns won 13-6 in Week 17 of 2025",
    )


def test_prompt_example_passes_the_guardrail():
    facts = _example_facts()
    assert render_fact_sheet(facts) in narrate_mod.EXAMPLES
    assert check_narration(narrate_mod.EXAMPLE_NARRATION, facts) is None


def test_mismatch_example_passes_the_guardrail():
    facts = narrate_mod.MISMATCH_EXAMPLE_FACTS
    assert render_fact_sheet(facts) in narrate_mod.EXAMPLES
    assert check_narration(narrate_mod.MISMATCH_EXAMPLE_NARRATION, facts) is None


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


def test_api_error_falls_back_to_none_without_a_final_sleep(settings_with_key):
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("api down at https://secret.example")
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        result = narrate_mod.generate(FACTS)
    assert result.text is None
    assert client.messages.create.call_count == narrate_mod.MAX_ATTEMPTS
    assert len(settings_with_key) == narrate_mod.MAX_ATTEMPTS - 1
    assert result.rejections == ["api error: RuntimeError"] * narrate_mod.MAX_ATTEMPTS


@pytest.mark.parametrize("error_cls, status", [
    (anthropic.AuthenticationError, 401),
    (anthropic.PermissionDeniedError, 403),
    (anthropic.BadRequestError, 400),
    (anthropic.NotFoundError, 404),
])
def test_non_retryable_api_error_stops_immediately(settings_with_key, error_cls, status):
    request = httpx.Request("POST", "https://api.example/v1/messages")
    error = error_cls("bad", response=httpx.Response(status, request=request), body=None)
    client = MagicMock()
    client.messages.create.side_effect = error
    with patch.object(narrate_mod.anthropic, "Anthropic", return_value=client):
        result = narrate_mod.generate(FACTS)
    assert result.text is None
    assert client.messages.create.call_count == 1
    assert settings_with_key == []
    assert result.rejections == [f"api error: {error_cls.__name__}"]


def test_cfb_prompt_carries_injury_guardrail():
    assert "injury" in narrate_mod._system_prompt("CFB").lower()


def test_dashes_are_rewritten():
    assert "—" not in narrate_mod._plain_punctuation("Texas — at home — rolls.")
