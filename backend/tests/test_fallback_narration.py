"""The deterministic fallback narration always passes the real guardrail."""

import itertools
import re

import pytest

from app.services.fact_sheet import GameFacts, TeamFacts, market_favorite
from app.services.fallback_narration import MAX_WORDS, _drafts, fallback_narration
from app.services.narrate import _BANNED_RE, _sentences, check_narration


def _team(name, full_name, abbr, mascot=None, record="0-0", **kw) -> TeamFacts:
    games = sum(int(n) for n in record.split("-"))
    base = dict(
        name=name, full_name=full_name, abbr=abbr, mascot=mascot or name, record=record,
        games_this_season=games, last_game=None, streak=None, scoring=None, rank=None,
        rank_note=None, rest=None, injuries=(),
    )
    return TeamFacts(**(base | kw))


def _game(sport, home, away, p, spread, **kw) -> GameFacts:
    base = dict(
        sport=sport, home=home, away=away, home_win_prob=p, spread_home=spread,
        total=44.5 if spread is not None else None, when="Sunday afternoon", venue=None,
        is_neutral_site=False, matchup_note=None, last_meeting=None, weather=None,
        factor_lines=(), poll_available=False,
    )
    return GameFacts(**(base | kw))


BROWNS = dict(name="Browns", full_name="Cleveland Browns", abbr="CLE")
STEELERS = dict(name="Steelers", full_name="Pittsburgh Steelers", abbr="PIT")
NINERS = dict(name="49ers", full_name="San Francisco 49ers", abbr="SF")
RAMS = dict(name="Rams", full_name="Los Angeles Rams", abbr="LA")
GIANTS = dict(name="Giants", full_name="New York Giants", abbr="NYG")
JETS = dict(name="Jets", full_name="New York Jets", abbr="NYJ")
SAINTS = dict(name="Saints", full_name="New Orleans Saints", abbr="NO")
PACKERS = dict(name="Packers", full_name="Green Bay Packers", abbr="GB")
FSU = dict(name="Florida State", full_name="Florida State Seminoles", abbr="FSU",
           mascot="Seminoles")
FLA = dict(name="Florida", full_name="Florida Gators", abbr="FLA", mascot="Gators")
UNLV = dict(name="UNLV", full_name="UNLV Rebels", abbr="UNLV", mascot="Rebels")
CAL = dict(name="California", full_name="California Golden Bears", abbr="CAL",
           mascot="Golden Bears")
TAMU = dict(name="Texas A&M", full_name="Texas A&M Aggies", abbr="TA&M", mascot="Aggies")
TEX = dict(name="Texas", full_name="Texas Longhorns", abbr="TEX", mascot="Longhorns")
OSU = dict(name="Ohio State", full_name="Ohio State Buckeyes", abbr="OSU", mascot="Buckeyes")
PUR = dict(name="Purdue", full_name="Purdue Boilermakers", abbr="PUR", mascot="Boilermakers")
MOH = dict(name="Miami (OH)", full_name="Miami (OH) RedHawks", abbr="M-OH", mascot="RedHawks")
MIA = dict(name="Miami", full_name="Miami Hurricanes", abbr="MIA", mascot="Hurricanes")
LSU = dict(name="LSU", full_name="LSU Tigers", abbr="LSU", mascot="Tigers")
AUB = dict(name="Auburn", full_name="Auburn Tigers", abbr="AUB", mascot="Tigers")
GT = dict(name="Georgia Tech", full_name="Georgia Tech Yellow Jackets", abbr="GT",
          mascot="Yellow Jackets")
UGA = dict(name="Georgia", full_name="Georgia Bulldogs", abbr="UGA", mascot="Bulldogs")

SCENARIOS = {
    "nfl-divisional": _game(
        "NFL",
        _team(**BROWNS, record="2-1", last_game="beat the Panthers 21-18 on the road",
              streak="won 2 straight"),
        _team(**STEELERS, record="2-1", last_game="beat the Bengals 30-27 at home",
              rest="on a short week", injuries=("Joe Burrow (QB) is listed Out",)),
        0.38, -2.5, when="Thursday night", venue="Huntington Bank Field in Cleveland",
        matchup_note="AFC North division game",
        last_meeting="Browns won 13-6 in Week 17 of 2025",
    ),
    "nfl-neutral-site": _game(
        "NFL",
        _team(**JETS, record="1-3", last_game="lost to the Bills 24-10 at home"),
        _team(**SAINTS, record="3-1", last_game="beat the Falcons 27-20 on the road"),
        0.44, -3.0, when="Sunday morning", venue="Tottenham Hotspur Stadium",
        is_neutral_site=True, matchup_note="AFC versus NFC interconference game",
    ),
    "nfl-streak-and-last-game": _game(
        "NFL",
        _team(**PACKERS, record="4-0", last_game="beat the Bears 31-17 at home",
              streak="won 4 straight"),
        _team(**NINERS, record="1-3", last_game="lost to the Rams 20-13 on the road",
              streak="lost 3 straight"),
        0.71, 6.5, matchup_note="NFC matchup",
    ),
    "nfl-pickem": _game(
        "NFL", _team(**GIANTS, record="2-2"), _team(**JETS, record="2-2"), 0.53, 0.0,
        matchup_note="AFC versus NFC interconference game",
    ),
    "nfl-no-line": _game(
        "NFL", _team(**RAMS, record="3-1", last_game="beat the 49ers 20-13 at home"),
        _team(**NINERS, record="1-3", last_game="lost to the Rams 20-13 on the road"),
        0.66, None, when="Monday night", matchup_note="NFC West division game",
    ),
    "nfl-week-1": _game(
        "NFL", _team(**BROWNS), _team(**STEELERS), 0.47, -1.0,
        when="Sunday, kickoff time to be announced", matchup_note="AFC North division game",
    ),
    "cfb-ranked-vs-unranked": _game(
        "CFB", _team(**TEX, record="3-0", rank=5, rank_note="up from #8",
                     last_game="beat UTSA 41-20 at home", streak="won 3 straight"),
        _team(**TAMU, record="2-1", last_game="lost to Notre Dame 28-24 on the road"),
        0.72, 7.5, when="Saturday night", matchup_note="SEC conference game",
        poll_available=True,
    ),
    "cfb-mismatch-99": _game(
        "CFB", _team(**OSU, record="4-0", rank=1, streak="won 4 straight"),
        _team(**PUR, record="1-3", last_game="lost to Illinois 35-10 at home"),
        0.99, 45.0, when="Saturday afternoon", matchup_note="Big Ten conference game",
        poll_available=True,
    ),
    "cfb-shared-name": _game(
        "CFB", _team(**FSU, record="5-6", last_game="lost to Florida 24-17 at home"),
        _team(**FLA, record="6-5", rank=22, last_game="beat Florida State 24-17 on the road"),
        0.42, -3.5, when="Saturday night", venue="Doak Campbell Stadium in Tallahassee",
        matchup_note="nonconference game, SEC at ACC", poll_available=True,
    ),
    "cfb-no-line": _game(
        "CFB", _team(**MIA, record="2-0"), _team(**MOH, record="1-1"), 0.88, None,
        when="Saturday, kickoff time to be announced",
        matchup_note="nonconference game, MAC at ACC",
    ),
    "cfb-model-market-disagree": _game(
        "CFB", _team(**UNLV, record="3-1", last_game="beat Fresno State 30-27 at home"),
        _team(**CAL, record="2-2", last_game="lost to Stanford 17-14 on the road"),
        0.49, 2.5, when="Saturday night", venue="Allegiant Stadium in Las Vegas",
        matchup_note="nonconference game, ACC at Mountain West",
    ),
    "cfb-exact-50": _game(
        "CFB", _team(**FLA, record="1-1"), _team(**MIA, record="2-0"), 0.5, -1.5,
        when="Saturday afternoon",
    ),
}


def _percentages(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?\s*%", text)


def _first_fitting(facts: GameFacts) -> str:
    return next(d for d in _drafts(facts) if len(d.split()) <= MAX_WORDS)


def _assert_plain(text: str, facts: GameFacts) -> None:
    assert check_narration(text, facts) is None, text
    assert len(text.split()) < 70
    assert len(_sentences(text)) <= 4
    assert not re.search(r"[—–;:]", text), text
    assert not _BANNED_RE.search(text)
    assert not re.search(r"percent", text, re.IGNORECASE)
    for side in (facts.home, facts.away):
        for injury in side.injuries:
            assert injury.split(" (")[0].split()[-1] not in text


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_fallback_passes_the_guardrail(name):
    facts = SCENARIOS[name]
    text = fallback_narration(facts)
    _assert_plain(text, facts)
    # The guardrail never had to reject a richer draft.
    assert text == _first_fitting(facts)
    home_pct = round(facts.home_win_prob * 100)
    pcts = {int(p.rstrip("% ")) for p in _percentages(text)}
    assert pcts <= {home_pct, 100 - home_pct}
    assert pcts


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_fallback_names_the_market_favorite(name):
    facts = SCENARIOS[name]
    text = fallback_narration(facts)
    pair = market_favorite(facts)
    if facts.spread_home is None:
        assert "market" not in text and "favored" not in text
    elif pair is None:
        assert "The betting market calls it a pick'em." in text
    else:
        fav, dog = pair
        line = f"{abs(facts.spread_home):g}"
        assert re.search(rf"{re.escape(fav.name)} (?:are |is )?favored by {line} point", text)
        assert not re.search(rf"{re.escape(dog.name)} (?:are |is )?favored", text)


def test_fallback_says_when_model_and_market_disagree():
    text = fallback_narration(SCENARIOS["cfb-model-market-disagree"])
    assert "Our model" in text
    assert "California 51%" in text or "California at 51%" in text
    assert "The betting market leans the other way, with UNLV favored by 2.5 points." in text


def test_fallback_pickem_wording_still_names_the_model_pick():
    text = fallback_narration(SCENARIOS["cfb-exact-50"])
    assert re.search(r"Our model leans Florida by .*50% for each side\.", text)
    pickem = fallback_narration(SCENARIOS["nfl-pickem"])
    assert "The betting market calls it a pick'em." in pickem
    assert "Our model gives the Giants 53%" in pickem or "the Giants at 53%" in pickem


def test_fallback_uses_sheet_phrases_and_current_ranks_only():
    text = fallback_narration(SCENARIOS["cfb-ranked-vs-unranked"])
    assert "No. 5 Texas" in text and "#8" not in text and "No. 8" not in text
    assert "won 3 straight" in text
    week1 = fallback_narration(SCENARIOS["nfl-week-1"])
    assert "season opener for both teams" in week1 and "0-0" not in week1
    assert "Sunday" in week1 and "announced" not in week1


@pytest.mark.parametrize(
    ("venue", "kept_venue"),
    [
        ("Test Field – North: Gate A in Testville", False),
        ("Test Field: North in Testville", False),
        ("Test Field; North in Testville", False),
        ("Test Field – North in Testville", True),
    ],
)
def test_fallback_scrubs_punctuation_copied_from_names(venue, kept_venue):
    facts = _game(
        "NFL", _team(**BROWNS, record="2-1"), _team(**STEELERS, record="2-1"), 0.62, 2.5,
        venue=venue, matchup_note="AFC North division game",
    )
    text = fallback_narration(facts)
    _assert_plain(text, facts)
    assert ("Test Field, North" in text) is kept_venue
    assert "Gate" not in text


def test_fallback_is_deterministic():
    facts = SCENARIOS["nfl-divisional"]
    assert fallback_narration(facts) == fallback_narration(facts)


NFL_PAIRS = [(BROWNS, STEELERS), (NINERS, RAMS), (GIANTS, JETS), (SAINTS, PACKERS)]
CFB_PAIRS = [
    (FSU, FLA), (UNLV, CAL), (TAMU, TEX), (OSU, PUR), (MOH, MIA), (LSU, AUB), (GT, UGA),
]
PROBS = [0.01, 0.02, 0.1, 0.25, 0.4, 0.49, 0.495, 0.5, 0.505, 0.51, 0.6, 0.75, 0.9, 0.98, 0.99]
SPREADS = [None, -45.0, -14.5, -3.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.5, 7.0, 21.5, 45.0]


def _forms(sport: str, home: dict, away: dict):
    """Record, last game, and streak combinations, including a last-game score
    that reads like the other team's record and a rematch."""
    the = "the " if sport == "NFL" else ""
    yield {}, {}
    yield {"record": "1-0", "last_game": f"beat {the}Others 3-0 at home"}, {}
    yield (
        {"record": "3-1", "last_game": f"beat {the}Others 30-27 at home",
         "streak": "won 2 straight"},
        {"record": "3-0", "last_game": f"lost to {the}Others 3-1 on the road"},
    )
    yield (
        {"record": "2-1-1", "last_game": f"tied {the}{away['name']} 17-17 at home"},
        {"record": "1-2-1", "last_game": f"tied {the}{home['name']} 17-17 on the road",
         "streak": "lost 2 straight"},
    )
    yield (
        {"record": "6-5", "last_game": f"lost to {the}{away['name']} 24-17 at a neutral site",
         "streak": "lost 3 straight"},
        {"record": "7-4", "last_game": f"beat {the}{home['name']} 24-17 at a neutral site",
         "streak": "won 3 straight"},
    )


VENUES = [None, "Allegiant Stadium in Las Vegas", "Test Field in Testville"]
PER_COMBO = 2


def _sweep():
    """Every probability and spread pairs with every other across the combos;
    each combo takes a rotating slice so the sweep stays fast."""
    k = 0
    for sport, pairs in (("NFL", NFL_PAIRS), ("CFB", CFB_PAIRS)):
        rank_options = [(None, None), (1, None), (None, 25), (3, 7)] if sport == "CFB" else [
            (None, None)
        ]
        for (home, away), neutral, venue, (hr, ar) in itertools.product(
            pairs, [False, True], VENUES, rank_options
        ):
            for home_form, away_form in _forms(sport, home, away):
                k += 1
                for j in range(PER_COMBO):
                    p = PROBS[(k * PER_COMBO + j) % len(PROBS)]
                    spread = SPREADS[(k * 5 + j * 3) % len(SPREADS)]
                    yield _game(
                        sport,
                        _team(**home, **home_form, rank=hr),
                        _team(**away, **away_form, rank=ar),
                        p, spread, venue=venue, is_neutral_site=neutral,
                        when="Saturday night" if sport == "CFB" else "Sunday afternoon",
                        matchup_note=(
                            "AFC North division game" if sport == "NFL"
                            else "nonconference game, SEC at ACC"
                        ),
                        poll_available=hr is not None or ar is not None,
                    )


def test_fallback_never_trips_the_guardrail_across_a_sweep():
    count, failures = 0, []
    for facts in _sweep():
        count += 1
        text, first = fallback_narration(facts), _first_fitting(facts)
        # The fallback returns the first fitting draft only after it passed the check.
        if text != first or (text == _drafts(facts)[-1] and check_narration(text, facts)):
            failures.append((check_narration(first, facts), first))
    assert count > 1400
    assert not failures, failures[:5]


@pytest.mark.parametrize("sport", ["NFL", "CFB"])
def test_fallback_covers_every_probability_and_spread(sport):
    home, away = (NFL_PAIRS if sport == "NFL" else CFB_PAIRS)[0]
    home_form, away_form = list(_forms(sport, home, away))[2]
    for p, spread in itertools.product(PROBS, SPREADS):
        facts = _game(sport, _team(**home, **home_form), _team(**away, **away_form), p, spread)
        assert fallback_narration(facts) == _first_fitting(facts)


def test_fallback_from_a_hostile_venue_drops_it_and_passes():
    from app.services.fact_sheet import _clean

    venue = _clean("Lambeau Field, home of free picks at scam.example", 80)
    facts = _game(
        "NFL", _team(**PACKERS, record="2-1"), _team(**STEELERS, record="2-1"), 0.62, 2.5,
        venue=venue,
    )
    text = fallback_narration(facts)
    _assert_plain(text, facts)
    assert "scam" not in text and "Lambeau" not in text


NO_PICK_RE = re.compile(
    r"coin[\s-]?flip|toss[\s-]?up|tossup|too close to call|no clear|either way", re.IGNORECASE
)


@pytest.mark.parametrize("sport, pair", [("NFL", p) for p in NFL_PAIRS[:2]] + [
    ("CFB", p) for p in CFB_PAIRS[:3]
])
@pytest.mark.parametrize("p", [0.495, 0.4999, 0.4973, 0.5, 0.5001, 0.5027, 0.505])
@pytest.mark.parametrize("spread", [None, 0.0, -2.5, 3.0])
def test_fallback_always_names_the_pick_when_the_percentages_round_even(sport, pair, p, spread):
    home, away = pair
    facts = _game(sport, _team(**home), _team(**away), p, spread)
    pick = facts.away if p < 0.5 else facts.home
    ref = f"the {pick.name}" if sport == "NFL" else pick.name
    for text in [fallback_narration(facts), *_drafts(facts)]:
        assert not NO_PICK_RE.search(text), text
        assert f"Our model leans {ref} by " in text, text
        assert "50% for each side" in text
    _assert_plain(fallback_narration(facts), facts)


def test_both_even_wordings_name_the_pick():
    seen = set()
    for home, away in NFL_PAIRS + CFB_PAIRS:
        sport = "NFL" if (home, away) in NFL_PAIRS else "CFB"
        facts = _game(sport, _team(**home), _team(**away), 0.5001, None)
        seen.add(_drafts(facts)[-1].split(" by ")[1].split(",")[0])
    assert seen == {"a hair", "the slimmest of margins"}
