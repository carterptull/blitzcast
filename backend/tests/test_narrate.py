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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Allegiant Stadium in Las Vegas", True),
        ("The Bills are favored by 3 points.", True),
        ("the line of scrimmage", False),
        ("Test Field in Testville", False),
    ],
)
def test_mentions_market(text, expected):
    assert narrate_mod.mentions_market(text) is expected


# A second, independent corpus written after the guardrail was tuned on the
# first one, in five new scenarios.
# S1: Packers at Bears, Packers favored by 3, model Bears 54%, injuries both sides.
S1_CHI = _team(
    "Bears", "Chicago Bears", "CHI", "Bears", "2-2",
    last_game="lost to the Lions 27-24 on the road",
    scoring="averaging 22.3 points and allowing 25.0 over the last 3 games",
    injuries=("Montez Sweat (DE) is listed Doubtful",),
)
S1_GB = _team(
    "Packers", "Green Bay Packers", "GB", "Packers", "3-1",
    last_game="beat the Vikings 31-17 at home", streak="won 3 straight", rest="on a short week",
    injuries=("Jaire Alexander (CB) is listed Out",),
)
S1 = _facts(
    S1_CHI, S1_GB, 0.54, -3.0, 41.5, sport="NFL", when="Sunday afternoon",
    venue="Soldier Field in Chicago", matchup_note="NFC North division game",
    last_meeting="Packers won 24-20 in Week 18 of 2025", weather="41 degrees, wind 14 mph",
    factor_lines=(
        "Bears: rest advantage", "Packers: betting market", "Bears: quarterback availability",
        "Packers: season-long team strength rating",
    ),
)
# S2: Florida at Florida State, a shared name word, both ranked, Florida favored by 2.5.
S2_FSU = _team(
    "Florida State", "Florida State Seminoles", "FSU", "Seminoles", "4-2", rank=14,
    rank_note="holding steady", last_game="beat Clemson 27-20 at home",
)
S2_UF = _team(
    "Florida", "Florida Gators", "UF", "Gators", "5-1", rank=9, rank_note="up from #12",
    last_game="beat LSU 34-28 on the road", streak="won 4 straight",
)
S2 = _facts(
    S2_FSU, S2_UF, 0.43, -2.5, 51.5, venue="Doak Campbell Stadium in Tallahassee",
    matchup_note="nonconference game, SEC at ACC",
    last_meeting="Florida won 31-11 in Week 14 of 2025", poll_available=True,
    factor_lines=("Florida: AP poll standing", "Florida: betting market"),
)
# S3: FCS Austin Peay at No. 3 Georgia, a 42.5-point mismatch with no total.
S3 = _facts(
    _team(
        "Georgia", "Georgia Bulldogs", "UGA", "Bulldogs", "5-0", rank=3,
        rank_note="holding steady", streak="won 5 straight",
        last_game="beat Kentucky 41-10 on the road",
    ),
    _team(
        "Austin Peay", "Austin Peay Governors", "APSU", "Governors", "2-3",
        last_game="lost to Eastern Kentucky 24-21 at home",
    ),
    0.99, 42.5, None, when="Saturday afternoon", venue="Sanford Stadium in Athens",
    matchup_note="nonconference game, UAC at SEC", poll_available=True,
    factor_lines=("Georgia: FBS versus FCS class gap", "Georgia: AP poll standing"),
)
# S4: Jaguars at Texans, a pick'em, model Texans 50.4%.
S4 = _facts(
    _team("Texans", "Houston Texans", "HOU", "Texans", "2-2",
          last_game="beat the Colts 20-17 at home"),
    _team("Jaguars", "Jacksonville Jaguars", "JAX", "Jaguars", "2-2",
          last_game="lost to the Titans 23-16 on the road"),
    0.504, 0.0, 44.5, sport="NFL", when="Sunday afternoon", venue="NRG Stadium in Houston",
    matchup_note="AFC South division game", weather="indoors",
)
# S5: Ball State at Miami (OH), no line posted.
S5 = _facts(
    _team("Miami (OH)", "Miami (OH) RedHawks", "M-OH", "RedHawks", "3-2",
          streak="won 2 straight", last_game="beat Kent State 35-13 at home"),
    _team("Ball State", "Ball State Cardinals", "BALL", "Cardinals", "1-4",
          last_game="lost to Toledo 28-14 on the road"),
    0.61, None, None, when="Tuesday night", matchup_note="MAC conference game",
    poll_available=True,
)

FRESH_TRUE = [
    ("It's an NFC North division game at Soldier Field, and the Packers roll in having "
     "won 3 straight. Green Bay is laying 3 on the road, but our model sides with Chicago "
     "at 54%.", S1),
    ("Division football on a Sunday afternoon in Chicago. The Packers are 3-point "
     "favorites, yet the model likes the Bears at 54%. Green Bay is on a short week after "
     "beating the Vikings 31-17.", S1),
    ("Can the Bears bounce back after falling 27-24 to the Lions? Our model thinks so, "
     "giving Chicago a 54% chance even with Green Bay favored by 3.", S1),
    ("The Packers have won 3 straight, and Vegas has them laying 3 points at Soldier "
     "Field. Our model disagrees, with the Bears at 54% at home. That 14 mph wind could "
     "make it a grind.", S1),
    ("It's 41 degrees with a 14 mph wind on the lakefront. Green Bay is without Jaire "
     "Alexander, and Chicago's Montez Sweat is doubtful. The model gives the Bears 54%, "
     "bucking a market that favors the Packers by 3.", S1),
    ("The Packers won 24-20 the last time these two met. Now they are favored by 3 on a "
     "short week, but our model leans Bears, 54% to 46%.", S1),
    ("Rivalry week in the NFC North! The Bears are getting 3 points at home, and our "
     "model actually has them winning 54% of the time.", S1),
    ("Short week, cold air, and a 3-1 Packers team favored by 3. Our model still backs "
     "the Bears at 54%, pointing to rest advantage and quarterback availability.", S1),
    ("Chicago sits at 2-2 and Green Bay at 3-1 heading into this one. The market makes "
     "the Packers a 3-point favorite. Our model flips it, Bears 54%.", S1),
    ("The hosts are getting 3, but our model has Chicago at 54%. Montez Sweat is listed "
     "Doubtful for the Bears, while the Packers will be without Jaire Alexander.", S1),
    ("Green Bay comes in hot, winners of 3 straight. The visitors are favored by 3, yet "
     "our model sees the Bears at 54% with the Packers on a short week.", S1),
    ("The over/under sits at 41.5 with wind in the forecast. Our model leans Chicago at "
     "54% despite the Packers laying 3.", S1),
    ("The Bears are 2-2 and coming off a 27-24 loss. Our model still has them at 54% "
     "against a Packers team favored by 3.", S1),
    ("Jaire Alexander is out for Green Bay, and that matters for the Chicago passing "
     "game. The model leans the Bears at 54%, even as the market lays 3 with the Packers.", S1),
    ("Bears and Packers in the NFC North on a Sunday afternoon! Green Bay is favored by "
     "3, but our model is on Chicago at 54%.", S1),
    ("The road team is favored by 3, but the model likes the hosts at 54%. Chicago gets "
     "the rest advantage with Green Bay on a short week.", S1),
    ("Wind at 14 mph and 41 degrees at kickoff. The Packers' Jaire Alexander is out, and "
     "our model makes Chicago a 54% pick as a 3-point home underdog.", S1),
    ("No. 9 Florida heads to Tallahassee to face No. 14 Florida State in a ranked rivalry "
     "showdown. The Gators are favored by 2.5, and our model agrees, giving them 57%.", S2),
    ("The Seminoles host the Gators on Saturday night with both teams ranked. Our model "
     "has Florida at 57% and Florida State at 43%. Vegas lists the Gators as 2.5-point "
     "favorites.", S2),
    ("Florida has climbed to #9, up from #12, and it brings a 5-1 record into Doak "
     "Campbell Stadium. Our model makes the Gators 57% favorites, matching a market that "
     "has them laying 2.5.", S2),
    ("Florida State gets 2.5 points at home in this one. Our model leans Florida, 57% to "
     "43%.", S2),
    ("The Gators won 31-11 in the last meeting. The model backs Florida at 57%, and the "
     "total sits at 51.5.", S2),
    ("The Seminoles are 4-2 and need a statement win at home. The model gives Florida "
     "State 43%, and the Gators lay 2.5.", S2),
    ("Is this the week Florida State flips the script? Our model says no, Florida 57%, "
     "and the books agree with the Gators favored by 2.5.", S2),
    ("Florida State is 4-2 and ranked #14. The Seminoles are getting 2.5 at home, and our "
     "model has them at 43%.", S2),
    ("Florida has won 4 straight, including a 34-28 win at LSU. Our model likes the "
     "Gators at 57% on the road.", S2),
    ("Florida State beat Clemson 27-20 and holds steady at No. 14. Still, the Gators are "
     "2.5-point favorites and our model has them at 57%.", S2),
    ("No. 3 Georgia welcomes FCS Austin Peay to Sanford Stadium on Saturday afternoon. "
     "The Bulldogs are 42.5-point favorites, and our model puts them at 99%.", S3),
    ("Austin Peay is getting 42.5 points in Athens, and that tells you everything. Our "
     "model gives Georgia a 99% chance.", S3),
    ("Georgia is 5-0 and holding steady at #3. Our model makes the Bulldogs a 99% pick "
     "against the Governors, who are getting 42.5.", S3),
    ("The class gap is the whole story here, FBS versus FCS. Georgia sits at 99% in our "
     "model, laying 42.5 points at home.", S3),
    ("Georgia has won 5 straight and is holding steady at No. 3 in the AP poll. Expect "
     "the Bulldogs to roll, our model says 99%.", S3),
    ("The Governors lost 24-21 to Eastern Kentucky last time out. Our model gives Austin "
     "Peay just 1%.", S3),
    ("An AFC South division game indoors at NRG Stadium, and Vegas calls it a pick'em. "
     "Our model barely leans Houston at 50%.", S4),
    ("Both teams sit at 2-2, and the market can't separate them. Our model has it a coin "
     "flip at 50%.", S4),
    ("The Jaguars and Texans meet with nothing between them in the market. The total sits "
     "at 44.5, and our model calls it 50-50.", S4),
    ("Coin-flip game in Houston. Our model gives the Texans 50% and the Jaguars 50%, and "
     "the books have it as a pick'em.", S4),
    ("Houston beat the Colts 20-17 at home, while Jacksonville lost to the Titans 23-16 "
     "on the road. Our model says 50% either way.", S4),
    ("Houston and Jacksonville are dead even in the market, and the total is 44.5. Our "
     "model has the Texans at 50%.", S4),
    ("It's a MAC conference game on Tuesday night, and the RedHawks have won 2 straight. "
     "Our model likes Miami (OH) at 61% against a 1-4 Ball State team.", S5),
    ("The Cardinals are 1-4 and need a spark. Our model gives the RedHawks a 61% chance "
     "at home.", S5),
    ("Miami (OH) is 3-2 and rolling. The model makes the RedHawks the favorite at 61%, "
     "leaving Ball State at 39%.", S5),
    ("Ball State is coming off a 28-14 loss to Toledo, and Miami (OH) has won 2 straight. "
     "Our model leans the RedHawks, 61% to 39%.", S5),
    ("Can Ball State pull the upset on the road? Our model gives the Cardinals just 39%.", S5),
    ("Miami (OH) beat Kent State 35-13 at home. The RedHawks are the pick at 61%.", S5),
    ("Ohio State walks into Austin as the road underdog by 1.5. Our model still trusts "
     "the Buckeyes at 55%.", FACTS),
    ("It's 97 degrees in Austin with a 12 mph wind. Texas is laying 1.5 at home, but the "
     "model leans Ohio State at 55%.", FACTS),
]

FRESH_FALSE = [
    ("The Bears are favored by 3 at home, and our model agrees at 54%.", S1),
    ("Green Bay is laying 3.5 on the road, but our model likes Chicago at 54%.", S1),
    ("The total sits at 44.5 in the wind. Our model leans the Bears at 54%.", S1),
    ("Our model gives the Packers 54% despite the short week.", S1),
    ("Our model likes the Packers in this one, and Vegas has Green Bay laying 3.", S1),
    ("Caleb Williams and the Bears need a win. Our model has Chicago at 54%.", S1),
    ("The 3-1 Bears host a Packers team that has won 3 straight. Our model has Chicago at "
     "54%.", S1),
    ("The Packers beat the Vikings 31-14 at home. Our model has the Bears at 54%.", S1),
    ("The Bears have lost 2 straight. Our model still has them at 54%.", S1),
    ("The Bears will be without Jaire Alexander, and our model has Chicago at 54%.", S1),
    ("The visitors are getting 3 points at Soldier Field. Our model likes Chicago at 54%.", S1),
    ("Our model likes the visitors at 54% in the NFC North.", S1),
    ("Green Bay is getting 3 on the road. Our model leans Chicago at 54%.", S1),
    ("Green Bay is favored by three, but our model likes Chicago at 54%.", S1),
    ("The Packers ride a three-game winning streak into Chicago. Our model has the Bears "
     "at 54%.", S1),
    ("The hosts are favored by 3, and our model agrees at 54%.", S1),
    ("Our model sides with Green Bay at 54%, and the market agrees.", S1),
    ("The over/under is 43.5 at Soldier Field. Our model has the Bears at 54%.", S1),
    ("The Packers make the trip down from Wisconsin. Our model has the Bears at 54%.", S1),
    ("The No. 1 Packers come to Chicago. Our model has the Bears at 54%.", S1),
    ("The Packers are on a short week, and our model gives them 54%.", S1),
    ("Packers pass rusher Montez Sweat is doubtful. Our model has the Bears at 54%.", S1),
    ("Montez Sweat is listed Doubtful for the Packers. Our model has the Bears at 54%.", S1),
    ("Green Bay's Montez Sweat is doubtful, and our model has the Bears at 54%.", S1),
    ("The Packers are the underdog on the road, but our model has the Bears at 54%.", S1),
    _known_limit(
        "The Bears won 24-20 the last time these teams met. Our model has Chicago at 54%.", S1,
        "who won the last meeting is not checked, only that the score is on the sheet",
    ),
    ("Matt LaFleur has the Packers rolling. Our model has the Bears at 54%.", S1),
    ("The road team is the underdog by 3. Our model has the Bears at 54%.", S1),
    ("Florida State is favored by 2.5 at home. Our model likes Florida at 57%.", S2),
    ("No. 9 Florida State hosts No. 14 Florida. Our model likes the Gators at 57%.", S2),
    ("Our model has Florida State at 57% at home.", S2),
    ("The Seminoles are laying 2.5 at home. Our model has Florida at 57%.", S2),
    ("Florida is getting 2.5 points on the road. Our model has the Gators at 57%.", S2),
    ("The Gators are 4-2 and ranked #9. Our model has Florida at 57%.", S2),
    ("Florida won 31-14 in the last meeting. Our model has the Gators at 57%.", S2),
    ("Florida State is missing its starting quarterback. Our model has Florida at 57%.", S2),
    ("The total is 52.5 in Tallahassee. Our model has Florida at 57%.", S2),
    ("The hosts are favored by 2.5. Our model has Florida at 57%.", S2),
    ("The Gators come in at No. 12. Our model has Florida at 57%.", S2),
    ("Florida State has won 3 straight. Our model has Florida at 57%.", S2),
    ("Our model favors the Seminoles at home, but Florida is favored by 2.5.", S2),
    ("Florida is a 3-point favorite. Our model has the Gators at 57%.", S2),
    ("Florida has won 5 straight. Our model has the Gators at 57%.", S2),
    ("Our model gives the visitors 43%, and the Gators are favored by 2.5.", S2),
    ("Georgia is favored by 41.5. Our model has the Bulldogs at 99%.", S3),
    ("The Governors are laying 42.5. Our model has Georgia at 99%.", S3),
    ("Gunner Stockton leads Georgia into this one. Our model has the Bulldogs at 99%.", S3),
    ("No. 2 Georgia rolls on. Our model has the Bulldogs at 99%.", S3),
    ("Our model gives Austin Peay 99% in this one.", S3),
    ("Georgia has won 6 straight. Our model has the Bulldogs at 99%.", S3),
    ("Georgia is 6-0. Our model has the Bulldogs at 99%.", S3),
    ("The total sits at 55.5. Our model has Georgia at 99%.", S3),
    ("Austin Peay is without its injured starting quarterback. Our model has Georgia at "
     "99%.", S3),
    ("The Texans are 1-point favorites at home. Our model has Houston at 50%.", S4),
    ("Houston is favored by 2.5 at home. Our model has the Texans at 50%.", S4),
    ("Our model gives the Jaguars 52% on the road.", S4),
    ("Vegas has the Jaguars as underdogs. Our model has it at 50%.", S4),
    ("The total is 47 indoors. Our model has the Texans at 50%.", S4),
    ("Houston beat the Colts 20-13 at home. Our model has the Texans at 50%.", S4),
    ("Miami (OH) is favored by 7 at home. Our model has the RedHawks at 61%.", S5),
    ("Vegas likes the RedHawks. Our model has them at 61%.", S5),
    ("The RedHawks are laying the points. Our model has them at 61%.", S5),
    ("Ball State is a road underdog. Our model has Miami (OH) at 61%.", S5),
    ("Our model gives Ball State 61% on the road.", S5),
    ("Ball State quarterback Kadin Semonza is questionable. Our model has Miami (OH) at "
     "61%.", S5),
    ("Miami (OH) has won 3 straight. Our model has the RedHawks at 61%.", S5),
    ("The Cardinals are 2-3. Our model has Miami (OH) at 61%.", S5),
    ("Ball State is the model's favorite on Tuesday night at 61%.", S5),
    ("Texas is getting 1.5 at home. Our model has Ohio State at 55%.", FACTS),
    ("Ohio State is laying 1.5 in Austin. Our model has the Buckeyes at 55%.", FACTS),
]


@pytest.mark.parametrize("text, facts", FRESH_TRUE)
def test_fresh_true_narration_is_accepted(text, facts):
    assert check_narration(text, facts) is None


@pytest.mark.parametrize("text, facts", FRESH_FALSE)
def test_fresh_false_narration_is_rejected(text, facts):
    assert check_narration(text, facts) is not None


# Ordinary sentence openers a studio analyst uses. The allowlist is broad plain
# English, not one word per past failure.
OPENERS = [
    "Coin", "Bragging", "Trouble", "Danger", "Advantage", "Mismatch", "Respect", "Desperation",
    "Bottom", "Simple", "Bold", "Trust", "Defending", "Nobody", "Sharp", "Fade", "Circle", "Gut",
    "Blowout", "Location", "Bounce", "Tune", "Translation", "Hungry", "Confidence", "Grind",
    "Toss", "Flip", "Margin", "Familiar", "Familiarity", "Plenty", "Lots", "Count", "Steady",
    "Payback", "Health", "Depth", "Lakefront", "Chilly", "Ranked", "Rested", "Speed", "Rivalry",
    "Tradition",
]


@pytest.mark.parametrize("word", OPENERS)
def test_plain_sentence_openers_pass(word):
    text = f"{word} is the word in Chicago. Our model has the Bears at 54%."
    assert check_narration(text, S1) is None


@pytest.mark.parametrize("name", [
    "Mahomes", "Rodgers", "Sweat", "Stockton", "LaFleur", "Kelce", "Burrow", "Purdy", "Herbert",
    "Hurts", "Swift", "Kiffin",
    "Caleb Williams", "Gunner Stockton", "Patrick Mahomes", "Josh Allen", "Kirby Smart",
    "Matt LaFleur", "Jordan Love", "Will Levis",
])
def test_invented_names_still_fail_at_sentence_start(name):
    text = f"{name} is the word in Tallahassee. Our model has Florida at 57%."
    reason = check_narration(text, S2)
    assert reason is not None and "not in the fact sheet" in reason


@pytest.mark.parametrize("text, facts", [
    # Pronouns resolve to the subject, not to a team named later in the clause.
    ("The Packers won 24-20 the last time these two met. Now they are favored by 3 on a short "
     "week, but our model leans Bears, 54% to 46%.", S1),
    ("The Bears are 2-2 and coming off a 27-24 loss. Our model still has them at 54% against a "
     "Packers team favored by 3.", S1),
    ("Our model gives the edge to the Bears at 54%.", S1),
    # 50-50 in a toss-up, and fronts and mindsets that are not scores.
    ("It's a 50-50 game indoors. Our model has the Texans at 50%.", S4),
    ("The Bears run a 4-3 defense. Our model has Chicago at 54%.", S1),
    ("Expect a 3-4 look from Chicago. Our model has the Bears at 54%.", S1),
    ("A 1-0 mindset is all the Seminoles need. Our model has Florida at 57%.", S2),
    # Ranks, records, and streaks said of their owners.
    ("No. 9 Florida visits No. 14 Florida State. Our model has the Gators at 57%.", S2),
    ("It's No.9 against No.14 tonight. Our model has Florida at 57%.", S2),
    ("Florida is up from #12 to #9. Our model has the Gators at 57%.", S2),
    ("Chicago sits at 2-2 and Green Bay at 3-1. Our model has the Bears at 54%.", S1),
    ("The Bears host a 3-1 Packers team. Our model has Chicago at 54%.", S1),
    ("Our model has the Bears at 54%, and Green Bay is 3-1.", S1),
    # Role phrases.
    ("The home side is getting 3, and our model has Chicago at 54%.", S1),
    # Times do not split sentences.
    ("Kickoff is 7:30 p.m. on Tuesday night. Ball State is 1-4. Miami (OH) is 3-2. Our model "
     "has the RedHawks at 61%.", S5),
])
def test_fix3_true_copy_is_accepted(text, facts):
    assert check_narration(text, facts) is None


def test_previous_rank_is_accepted_when_it_is_the_teams():
    fsu = replace(S2_FSU, rank=11, rank_note="up from #14")
    facts = replace(S2, home=fsu)
    assert check_narration("Florida State is up from No. 14 after beating Clemson.", facts) is None


@pytest.mark.parametrize("text, facts, fragment", [
    ("It's a 50-50 game. Our model has the Bears at 54%.", S1, "50-50"),
    ("The Bears are 50-50 at home. Our model has the Bears at 54%.", S1, "50-50"),
    # Injury attribution through the city, "missing", and the surname alone.
    ("Green Bay's Montez Sweat is doubtful. Our model has the Bears at 54%.", S1, "Montez Sweat"),
    ("The Packers are missing Montez Sweat. Our model has the Bears at 54%.", S1, "Montez Sweat"),
    ("Sweat is doubtful for the Packers. Our model has the Bears at 54%.", S1, "Montez Sweat"),
    ("Green Bay, without Montez Sweat, comes in on a short week. Our model has the Bears at "
     "54%.", S1, "Montez Sweat"),
    ("The Bears lost Jaire Alexander. Our model has Chicago at 54%.", S1, "Jaire Alexander"),
    ("The Packers are without Sweat. Our model has the Bears at 54%.", S1, "Montez Sweat"),
    # Ranks: current ranks only, said of their owner.
    ("No. 9 Florida State hosts No. 14 Florida. Our model likes the Gators at 57%.", S2,
     "No. 9 for Florida State"),
    ("The Gators come in at No. 12. Our model has Florida at 57%.", S2, "No. 12"),
    ("The Seminoles are No. 9. Our model has Florida at 57%.", S2, "No. 9"),
    ("Florida State is up from #12. Our model has Florida at 57%.", S2, "#12"),
    # Records and streaks said of the wrong team.
    ("The Gators are 4-2 and ranked #9. Our model has Florida at 57%.", S2, "4-2 for Florida"),
    ("The 3-1 Bears host a Packers team that has won 3 straight. Our model has Chicago at 54%.",
     S1, "3-1 for Bears"),
    ("The Packers come in at 2-2. Our model has the Bears at 54%.", S1, "2-2 for Packers"),
    ("Florida State has won 4 straight. Our model has Florida at 57%.", S2, "won 4 straight"),
    # Role phrases.
    ("The home side is laying 3. Our model has Chicago at 54%.", S1, "betting favorite"),
    ("The home squad is favored by 3. Our model has Chicago at 54%.", S1, "betting favorite"),
    ("The visiting squad is getting 3. Our model has Chicago at 54%.", S1, "getting points"),
    # A pronoun still resolves to the sentence's subject.
    ("The Packers are on a short week, and our model gives them 54%.", S1, "Packers"),
])
def test_fix3_false_copy_is_rejected(text, facts, fragment):
    reason = check_narration(text, facts)
    assert reason is not None and fragment in reason, reason


def test_city_names_attribute_injuries():
    kc = _team("Chiefs", "Kansas City Chiefs", "KC", "Chiefs",
               injuries=("Chris Jones (DT) is listed Out",))
    tb = _team("Buccaneers", "Tampa Bay Buccaneers", "TB", "Buccaneers")
    facts = _facts(tb, kc, 0.45, -2.5, 47.5, sport="NFL")
    reason = check_narration("Tampa Bay's Chris Jones is out. Our model has Kansas City at 55%.",
                             facts)
    assert reason is not None and "Chris Jones" in reason
    assert check_narration(
        "Kansas City's Chris Jones is out, and our model has Kansas City at 55%.", facts
    ) is None


def test_shared_city_is_not_a_team_mention():
    giants = _team("Giants", "New York Giants", "NYG", "Giants")
    jets = _team("Jets", "New York Jets", "NYJ", "Jets")
    facts = _facts(giants, jets, 0.6, 2.5, sport="NFL")
    # "New York" names neither team, so the claim stays with the team named before it.
    assert check_narration("The Giants are favored by 2.5 in New York.", facts) is None
    reason = check_narration("The Jets are favored by 2.5 in New York.", facts)
    assert reason is not None and "betting favorite" in reason
