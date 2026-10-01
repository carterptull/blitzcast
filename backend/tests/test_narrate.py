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
        games_this_season=sum(int(n) for n in record.split("-")), last_game=None, streak=None,
        scoring=None,
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


# Realistic scenarios for the true / false narration corpus.
# A: Ohio State at Texas, Texas favored by 1.5, model Ohio State 55%.
A_TEX = _team(
    "Texas", "Texas Longhorns", "TEX", "Longhorns", "4-0", rank=3, rank_note="holding steady",
    last_game="beat Baylor 38-17 at home", streak="won 4 straight",
)
A_OSU = _team(
    "Ohio State", "Ohio State Buckeyes", "OSU", "Buckeyes", "4-0", rank=2,
    rank_note="up from #4", last_game="beat Penn State 27-24 on the road",
    streak="won 4 straight",
)
A = _facts(
    A_TEX, A_OSU, 0.45, 1.5, 49.5, venue="DKR-Texas Memorial Stadium in Austin",
    matchup_note="nonconference game, Big Ten at SEC", weather="97 degrees, wind 12 mph",
    factor_lines=("Texas: betting market", "Ohio State: AP poll standing"), poll_available=True,
)
# B: Bengals at Ravens, Ravens favored by 6.5, model Ravens 71%, Bengals injuries.
B_BAL = _team(
    "Ravens", "Baltimore Ravens", "BAL", "Ravens", "3-1",
    last_game="beat the Browns 31-10 on the road", streak="won 3 straight",
    scoring="averaging 29.3 points and allowing 15.7 over the last 3 games",
)
B_CIN = _team(
    "Bengals", "Cincinnati Bengals", "CIN", "Bengals", "2-2",
    last_game="lost to the Steelers 24-20 at home", streak="lost 2 straight",
    rest="on a short week",
    injuries=("Joe Burrow (QB) is listed Out", "Ja'Marr Chase (WR) is listed Doubtful"),
)
B = _facts(
    B_BAL, B_CIN, 0.71, 6.5, 44.5, sport="NFL", when="Sunday afternoon",
    venue="M&T Bank Stadium in Baltimore", matchup_note="AFC North division game",
    last_meeting="Ravens won 27-24 in Week 10 of 2025", weather="58 degrees, wind 9 mph",
    factor_lines=(
        "Ravens: quarterback availability", "Ravens: betting market",
        "Ravens: point differential over the last 5 games",
    ),
)
# C: Kansas State at Kansas, no line, model Kansas State 61%.
C_KU = _team(
    "Kansas", "Kansas Jayhawks", "KU", "Jayhawks", "2-2",
    last_game="lost to Baylor 31-28 on the road",
)
C_KSU = _team(
    "Kansas State", "Kansas State Wildcats", "KSU", "Wildcats", "3-1", rank=18,
    rank_note="up from #22", last_game="beat Arizona 35-14 at home", streak="won 3 straight",
)
C = _facts(
    C_KU, C_KSU, 0.39, None, None, venue="David Booth Kansas Memorial Stadium in Lawrence",
    matchup_note="Big 12 conference game", when="Saturday afternoon",
    last_meeting="Kansas State won 29-27 in Week 9 of 2025", poll_available=True,
)
# D: Michigan State at Ohio State, Ohio State favored by 14.5, model Ohio State 88%.
D = _facts(
    _team("Ohio State", "Ohio State Buckeyes", "OSU", "Buckeyes", "4-0"),
    _team("Michigan State", "Michigan State Spartans", "MSU", "Spartans", "2-2"),
    0.88, 14.5, 52.5, venue="Ohio Stadium in Columbus", matchup_note="Big Ten conference game",
)


def _known_limit(text, facts, why):
    return pytest.param(text, facts, marks=pytest.mark.xfail(strict=True, reason=why))


# Narrations fully true to their fact sheets.
CORPUS_TRUE = [
    ("Number 2 at number 3 under the lights in Austin. Our model leans Ohio State at 55%, even "
     "with Texas favored by 1.5 at home.", A),
    ("The Buckeyes roll into Austin at 4-0 after a 27-24 win at Penn State. Texas is laying "
     "1.5, but our model has Ohio State at 55%.", A),
    ("Big Ten at SEC on Saturday night, and it does not get bigger than this. The Longhorns are "
     "1.5-point favorites at home. Our model disagrees and gives the Buckeyes 55%.", A),
    ("Texas hosts Ohio State, but the Buckeyes are the model's pick at 55%.", A),
    ("Texas has won 4 straight, including a 38-17 win over Baylor. Still, the model likes Ohio "
     "State at 55%, while Vegas has the Longhorns by 1.5.", A),
    ("It is 97 degrees in Austin and the stakes are just as hot. Ohio State is getting 1.5 "
     "points, yet our model makes the Buckeyes a 55% pick.", A),
    ("Ohio State's 4-0 start meets Texas' 4-0 start at DKR-Texas Memorial Stadium. The model "
     "gives the Buckeyes 55% to the Longhorns' 45%.", A),
    ("The Longhorns' home crowd will be loud. Our model still sides with Ohio State at 55%, and "
     "the market only has Texas favored by 1.5.", A),
    ("A top-3 showdown in Austin. Texas is the slight favorite in the market at 1.5, but the "
     "model has Ohio State winning 55% of the time.", A),
    ("Ohio State climbed to No. 2 this week. The Buckeyes walk into Austin as the model's "
     "favorite at 55%, with the total at 49.5.", A),
    ("Saturday night in Austin, and the model is on the road team. Ohio State sits at 55%, "
     "Texas at 45%.", A),
    ("Texas comes in at 4-0 and ranked No. 3, and the Longhorns are laying 1.5 points. Our "
     "model goes the other way with Ohio State at 55%.", A),
    ("Heat, wind, and two unbeaten teams. The Buckeyes are 1.5-point underdogs, but our model "
     "makes them 55% favorites.", A),
    ("Wind at 12 mph and 97 degrees at kickoff. Texas is favored by 1.5 points, and the model "
     "still backs Ohio State at 55%.", A),
    ("The Buckeyes are 1.5-point underdogs, but our model makes them 55% favorites.", A),
    ("Texas hosts Ohio State, but our model likes the visitors at 55%.", A),
    ("Texas hosts Ohio State, and our model likes the road team at 55%.", A),
    ("Ohio State visits Texas, and the model likes them at 55%.", A),
    _known_limit(
        "Texas hosts Ohio State tonight, but our model likes them at 55%.", A,
        "pronouns fall back to the first team named in the sentence",
    ),
    ("Ohio State is the pick, 55% to win in Austin against a Texas team favored by 1.5.", A),
    ("Despite the Longhorns laying 1.5, the model takes Ohio State at 55%.", A),
    ("The model takes Ohio State at 55% despite Texas laying 1.5.", A),
    ("Our model gives Texas just a 45% chance, with Ohio State at 55%.", A),
    ("A 55% chance for Ohio State, per our model, even as Texas lays 1.5.", A),
    ("Texas -1.5 at home. Our model says Ohio State at 55%.", A),
    ("Ohio State +1.5 on the road, and the model has the Buckeyes winning 55% of the time.", A),
    ("The books make Texas a 1.5-point favorite. The model leans the other way, Ohio State at "
     "55%.", A),
    ("Ohio State is a 1.5-point dog in Austin, but the model likes the Buckeyes at 55%.", A),
    ("Two unbeaten teams, one at 4-0 in the Big Ten and one at 4-0 in the SEC. Our model leans "
     "Ohio State at 55%.", A),
    ("Unbeaten versus unbeaten in Austin. Our model has Ohio State at 55%.", A),
    ("Revenge is not on the sheet, but stakes are. Our model has Ohio State at 55%.", A),
    ("Rain is not a factor, heat is. Our model has Ohio State at 55%.", A),
    ("Momentum belongs to the Buckeyes after a 27-24 win at Penn State. Our model has them at "
     "55%.", A),
    ("Huge game in Austin. Our model has Ohio State at 55%.", A),
    ("Massive stakes, top-3 teams. Our model has Ohio State at 55%.", A),
    ("Hot and windy in Austin. Our model has Ohio State at 55%.", A),
    ("Undefeated Texas hosts undefeated Ohio State. Our model has the Buckeyes at 55%.", A),
    ("Ranked No. 2 against No. 3. The model gives Ohio State 55%.", A),
    ("Statement game for the Buckeyes. The model gives Ohio State 55%.", A),
    ("The Longhorns are favored, but our model gives the Buckeyes 55%.", A),
    ("Both teams are 4-0. Vegas makes Texas a slight favorite, and our model leans Ohio State "
     "at 55%.", A),
    ("AFC North football in Baltimore on Sunday afternoon. The Ravens have won 3 straight and "
     "our model likes them at 71%.", B),
    ("Cincinnati is without Joe Burrow, who is listed Out. The Ravens are 6.5-point favorites, "
     "and our model has Baltimore at 71%.", B),
    ("The Bengals have lost 2 straight and come in on a short week. Baltimore is laying 6.5 at "
     "home, and the model makes the Ravens a 71% pick.", B),
    ("Joe Burrow is out and Ja'Marr Chase is doubtful for the Bengals. Our model gives the "
     "Ravens 71%, with the total at 44.5.", B),
    ("The Ravens beat the Browns 31-10 last week, while the Bengals fell to the Steelers 24-20. "
     "Our model leans Baltimore at 71%.", B),
    ("Baltimore won 27-24 in Week 10 of 2025, the last time these two met. This time the model "
     "has the Ravens at 71%, and Vegas has them favored by 6.5.", B),
    ("The Bengals' offense looks very different without Joe Burrow. Cincinnati is getting 6.5 "
     "points, and our model gives them just 29%.", B),
    ("Division game at M&T Bank Stadium. The Ravens are averaging 29.3 points over their last 3 "
     "games, and the model likes them at 71%.", B),
    ("Short week for the Bengals, and it shows on the injury report with Joe Burrow listed Out. "
     "Our model puts Baltimore at 71%.", B),
    ("Ravens minus 6.5 at home. Our model is even more sure, giving Baltimore 71%.", B),
    ("Baltimore gets a break with Joe Burrow listed Out. Our model has the Ravens at 71%.", B),
    ("The Ravens will not see Joe Burrow on Sunday afternoon. Our model has Baltimore at 71%.",
     B),
    ("Big edge for the Ravens with Joe Burrow out. Baltimore is laying 6.5.", B),
    ("Division rivals meet in Baltimore. The Ravens are 6.5-point favorites and our model has "
     "them at 71%.", B),
    ("Bad timing for Cincinnati, on a short week with Joe Burrow out. Our model has the Ravens "
     "at 71%.", B),
    ("Short week, no Joe Burrow, and a road trip to Baltimore. The model gives Cincinnati 29%.",
     B),
    ("Sunday afternoon in Baltimore, 58 degrees with a 9 mph wind. The Ravens are 71% in our "
     "model.", B),
    ("Revenge game for the Bengals after a 27-24 loss in Week 10 of 2025. Our model still has "
     "Baltimore at 71%.", B),
    ("Points have come easy for Baltimore, 29.3 a game over the last 3. Our model has the "
     "Ravens at 71%.", B),
    ("The Ravens are favored by 6.5 and the total sits at 44.5. Our model makes Baltimore a 71% "
     "pick.", B),
    ("Cincinnati comes in at 2-2. Baltimore at 3-1 is the 71% side.", B),
    ("It is a Big 12 conference game in Lawrence. Our model likes Kansas State at 61%.", C),
    ("Kansas State brings a 3-game win streak into Lawrence. The Wildcats beat Arizona 35-14 "
     "last week, and our model has them at 61%.", C),
    ("Kansas lost to Baylor 31-28 on the road last time out. The Jayhawks sit at 39% in our "
     "model against the No. 18 Wildcats.", C),
    ("Kansas State won 29-27 in Week 9 of 2025. The model leans the Wildcats again at 61%.", C),
    ("Kansas hosts Kansas State on Saturday afternoon, but the model likes the visitors at 61%.",
     C),
    ("The Wildcats are up from No. 22 to No. 18 in the AP poll. Our model makes Kansas State a "
     "61% favorite on the road.", C),
    ("Kansas is the underdog in our model at 39%, and the Wildcats have won 3 straight.", C),
    ("Kansas State is the No. 18 team in the country. The Wildcats are 61% in our model, Kansas "
     "39%.", C),
    ("Kansas is at home, but our model likes the Wildcats at 61%.", C),
    ("Rivalry game in Lawrence. No line is posted, but our model has Kansas State at 61%.", C),
    ("Michigan State visits Ohio Stadium, and the Buckeyes are 14.5-point favorites. Our model "
     "has Ohio State at 88%.", D),
    ("The Spartans are getting 14.5 points in Columbus. Our model gives Michigan State only "
     "12%.", D),
    ("Michigan State visits Ohio State, and the Spartans are getting 14.5. Our model has the "
     "Buckeyes at 88%.", D),
    ("Ohio State is laying 14.5 against Michigan State. Our model has the Buckeyes at 88%.", D),
]


@pytest.mark.parametrize("text, facts", CORPUS_TRUE)
def test_corpus_true_narration_is_accepted(text, facts):
    assert check_narration(text, facts) is None


# Narrations with one false or forbidden claim each.
CORPUS_FALSE = [
    ("Ohio State is favored by 1.5 on the road, and our model likes the Buckeyes at 55%.", A),
    ("Vegas has Texas favored by 3.5, but our model likes Ohio State at 55%.", A),
    ("The Longhorns are the model's pick at 55% in Austin.", A),
    ("Texas hosts Ohio State, and the model likes the Longhorns to protect home turf at 55%.", A),
    ("Arch Manning and Texas host Ohio State, and our model leans the Buckeyes at 55%.", A),
    ("Steve Sarkisian has Texas at 4-0. Our model leans Ohio State at 55%.", A),
    ("Ohio State comes in at 5-0. Our model leans the Buckeyes at 55%.", A),
    ("Texas has won 6 straight. Our model leans the Buckeyes at 55%.", A),
    ("Texas is missing its starting quarterback. Our model likes Ohio State at 55%.", A),
    ("Texas is favored by one and a half points. Our model likes Ohio State at 55%.", A),
    ("Texas is getting 1.5 at home, but our model likes Ohio State at 55%.", A),
    ("The Buckeyes are laying 1.5 in Austin, and our model likes them at 55%.", A),
    ("Texas hosts Ohio State, but the Longhorns are the model's pick at 55%.", A),
    ("The total is 52.5 in Austin, and our model likes Ohio State at 55%.", A),
    ("Ohio State is a 1.5-point favorite in Austin. Our model agrees at 55%.", A),
    ("The Longhorns are underdogs at home, and the model likes Ohio State at 55%.", A),
    ("Vegas likes Ohio State by 1.5, and so does our model at 55%.", A),
    ("In Columbus on Saturday night, the model likes Ohio State at 55%.", A),
    ("Ohio State won the last meeting 24-21. Our model leans the Buckeyes at 55%.", A),
    ("Texas is the betting underdog, but our model likes Ohio State at 55%.", A),
    ("Texas has the edge in Vegas, but the Buckeyes are 55% to win and favored by 1.5.", A),
    ("Our model likes Ohio State at 55%. The Longhorns are getting the points at home.", A),
    ("Our model likes Ohio State at 55%. Texas is +1.5 at home.", A),
    ("Ohio State is the underdog in Austin. Our model likes Texas at 55%.", A),
    ("Ohio State is giving 1.5 on the road. Our model likes the Buckeyes at 55%.", A),
    ("Texas sits at plus 1.5 at home. Our model likes Ohio State at 55%.", A),
    ("Vegas has Ohio State at minus 1.5. Our model likes the Buckeyes at 55%.", A),
    ("The over/under is 52 in Austin. Our model likes Ohio State at 55%.", A),
    ("Texas is favored by a field goal. Our model likes Ohio State at 55%.", A),
    ("Ohio State is laying a point and our model likes the Buckeyes at 55%.", A),
    ("Texas has a 55% chance in our model.", A),
    ("The Longhorns, whom our model gives 55%, host Ohio State.", A),
    ("Our model picks Texas to win in Austin, 55% to 45%.", A),
    ("Our model sides with the Longhorns, even with Ohio State at 55%.", A),
    ("Texas is our model's pick in Austin. The Buckeyes are at 45%.", A),
    _known_limit(
        "Our model thinks the Longhorns win this one. Texas is laying 1.5.", A,
        "a model pick with no percentage and no favorite wording is not parsed",
    ),
    ("The model's favorite is Texas at home. Vegas agrees, laying 1.5.", A),
    ("The Buckeyes are the betting favorite in Austin, and our model likes them at 55%.", A),
    ("The market likes the Buckeyes on the road. Our model likes them at 55%.", A),
    ("OSU -1.5 in Austin. Our model likes the Buckeyes at 55%.", A),
    ("Texas is the No. 1 team in the country. Our model likes Ohio State at 55%.", A),
    ("The Buckeyes have the edge with the books. Our model likes them at 55%.", A),
    ("Our model gives the Longhorns the nod at 55%.", A),
    ("Texas hosts Ohio State, but our model likes the hosts at 55%.", A),
    ("Baltimore is without Joe Burrow, and our model likes the Ravens at 71%.", B),
    ("The Bengals are 6.5-point favorites on the road. Our model likes Baltimore at 71%.", B),
    ("The Ravens are favored by 7 at home, and our model likes them at 71%.", B),
    ("Lamar Jackson and the Ravens have won 3 straight. Our model likes Baltimore at 71%.", B),
    ("The Bengals have lost 3 straight. Our model likes Baltimore at 71%.", B),
    ("Cincinnati is a 71% pick in our model, but Joe Burrow is listed Out.", B),
    ("The Ravens are getting 6.5 at home, and our model likes them at 71%.", B),
    ("Baltimore is 4-0 and our model likes the Ravens at 71%.", B),
    ("The Ravens beat the Browns 34-10 last week. Our model has Baltimore at 71%.", B),
    ("Baltimore is favored by six and a half. Our model has the Ravens at 71%.", B),
    ("Joe Burrow is listed Out for the Ravens. Our model has Baltimore at 71%.", B),
    ("The Ravens are without Joe Burrow. Our model has Baltimore at 71%.", B),
    ("Baltimore's Joe Burrow is listed Out. Our model has the Ravens at 71%.", B),
    ("Ravens quarterback Joe Burrow is listed Out. Our model has Baltimore at 71%.", B),
    _known_limit(
        "The Ravens, with Joe Burrow out, are 71% in our model.", B,
        "\"with <name> out\" is not read as attribution, true copy uses it for either team",
    ),
    _known_limit(
        "Ja'Marr Chase is out for the Bengals. Our model has the Ravens at 71%.", B,
        "the listed status (Out vs Doubtful) is not checked",
    ),
    _known_limit(
        "Joe Burrow is listed Doubtful. Our model has the Ravens at 71%.", B,
        "the listed status (Out vs Doubtful) is not checked",
    ),
    ("The Ravens are 6.5-point underdogs at home. Our model has Baltimore at 71%.", B),
    ("Cincinnati is the 71% side in our model.", B),
    ("Our model has Baltimore at 81%.", B),
    ("The Ravens are favored by 6 at home. Our model has Baltimore at 71%.", B),
    _known_limit(
        "The Ravens haven't lost at home all season. Our model has Baltimore at 71%.", B,
        "invented history without a number is not checkable",
    ),
    ("The Wildcats are favored by 3 in Lawrence, and our model likes them at 61%.", C),
    ("Vegas and our model agree on Kansas State at 61%.", C),
    ("Kansas hosts Kansas State, and the model likes the Jayhawks at 61%.", C),
    ("Kansas State is the underdog in our model at 39%.", C),
    ("Kansas State is the model's favorite in Manhattan at 61%.", C),
    ("Kansas has won 2 straight. Our model likes Kansas State at 61%.", C),
    _known_limit(
        "The Jayhawks are without their starting quarterback. Our model likes Kansas State at "
        "61%.", C, "\"without\" alone is too common to read as an injury claim",
    ),
    _known_limit(
        "Kansas State is favored on the road. Our model has the Wildcats at 61%.", C,
        "a bare \"favored\" with no line reads as the model's pick, which it is",
    ),
    ("The Wildcats are the No. 12 team. Our model has Kansas State at 61%.", C),
    ("Our model makes Kansas the 61% pick against Kansas State.", C),
    ("Michigan State is favored by 14.5 on the road. Our model has Ohio State at 88%.", D),
    ("Michigan State is 88% in our model at Ohio Stadium.", D),
    _known_limit(
        "State is favored by 14.5 in Columbus. Our model has Ohio State at 88%.", D,
        "a generic name word alone identifies neither team",
    ),
    ("Ohio State is getting 14.5 at home. Our model has the Buckeyes at 88%.", D),
    _known_limit(
        "Michigan State hosts Ohio State. Our model has the Buckeyes at 88%.", D,
        "who hosts is not checked",
    ),
    ("The Spartans are laying 14.5 in Columbus. Our model has Ohio State at 88%.", D),
    ("Ohio State hosts Michigan State and the Spartans are 14.5-point favorites. Our model has "
     "the Buckeyes at 88%.", D),
]


@pytest.mark.parametrize("text, facts", CORPUS_FALSE)
def test_corpus_false_narration_is_rejected(text, facts):
    assert check_narration(text, facts) is not None


@pytest.mark.parametrize("text, fragment", [
    ("Joe Burrow is listed Out for the Ravens.", "wrong team"),
    ("The Ravens are without Joe Burrow.", "wrong team"),
    ("Baltimore's Joe Burrow is listed Out.", "wrong team"),
    ("Texas hosts Ohio State, but our model likes the hosts at 55%.", "the model has Texas"),
    ("Ohio State comes in at 5-0.", "5-0"),
    ("Texas has won 6 straight.", "6 straight"),
    ("The Ravens beat the Browns 34-10 last week.", "34-10"),
    ("Ohio State won the last meeting 24-21.", "24-21"),
    ("Texas is the No. 1 team in the country.", "No. 1"),
    ("The Wildcats are ranked #12.", "#12"),
    ("The Bengals have lost 3 straight.", "lost 3 straight"),
])
def test_new_rejections_name_the_claim(text, fragment):
    facts = A if "Texas" in text or "Ohio State" in text else B
    if "Wildcats" in text:
        facts = C
    reason = check_narration(text, facts)
    assert reason is not None and fragment in reason, reason


@pytest.mark.parametrize("name", [
    "Jackson", "Stroud", "Herbert", "Purdy", "Kiffin", "Tuscaloosa", "Pittsburgh", "Norman",
])
def test_more_invented_names_stay_rejected(name):
    reason = check_narration(f"Huge night in Austin with {name} in the building.", A)
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
