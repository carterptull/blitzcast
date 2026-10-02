"""Deterministic "From the booth" copy for when no AI draft survives the fact
check. Every phrase is built from the fact sheet, so the text passes the same
guardrail the AI narration does: digits only, no injuries or player names, no
market talk without a posted line. `minimal_narration` is the last resort when
not even the fact sheet can be built."""

import re

from app.services.fact_sheet import GameFacts, TeamFacts, market_favorite
from app.services.narrate import check_narration, mentions_market, plain_punctuation

MAX_WORDS = 69
# Copied venue or team names can carry these; the guardrail does not reject them.
_UNSAFE_PUNCTUATION_RE = re.compile(r"[;:]")


def _plural(facts: GameFacts) -> bool:
    # NFL short names are nicknames ("the Bills"); CFB short names are schools.
    return facts.sport == "NFL"


def _ref(team: TeamFacts, facts: GameFacts, rank: bool = True) -> str:
    if facts.sport == "CFB" and rank and team.rank:
        return f"No. {team.rank} {team.name}"
    return f"the {team.name}" if _plural(facts) else team.name


def _verb(facts: GameFacts, plural: str, singular: str) -> str:
    return plural if _plural(facts) else singular


def _variant(facts: GameFacts, bit: int) -> int:
    seed = sum(ord(c) for c in facts.home.abbr + facts.away.abbr)
    return (seed >> bit) & 1


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _setting(facts: GameFacts, venue: bool) -> str:
    # "Allegiant Stadium in Las Vegas" reads as market talk when no line is posted.
    if facts.spread_home is None and facts.venue and mentions_market(facts.venue):
        venue = False
    day = facts.when.split(",")[0].strip()
    home, away = _ref(facts.home, facts), _ref(facts.away, facts)
    if facts.is_neutral_site:
        where = f" on neutral ground at {facts.venue}" if venue and facts.venue else (
            " at a neutral site"
        )
        core = f"{away} and {home} meet{where}"
    else:
        where = f" at {facts.venue}" if venue and facts.venue else ""
        core = f"{away} {_verb(facts, 'visit', 'visits')} {home}{where}"
    note = facts.matchup_note.split(",")[0].strip() if facts.matchup_note else ""
    tail = f" in this {note}" if note else ""
    if day and _variant(facts, 0):
        return f"{day}, {core}{tail}."
    when = f" on {day}" if day else ""
    return f"{_cap(core)}{when}{tail}."


def _model_pcts(facts: GameFacts) -> tuple[int, int]:
    return round(facts.home_win_prob * 100), round((1 - facts.home_win_prob) * 100)


def _model_favorite(facts: GameFacts) -> TeamFacts | None:
    home_pct, away_pct = _model_pcts(facts)
    if home_pct == away_pct:
        return None
    return facts.home if home_pct > away_pct else facts.away


def _model(facts: GameFacts) -> str:
    fav = _model_favorite(facts)
    if fav is None:
        return "Our model sees a coin flip, with 50% for each side."
    dog = facts.away if fav is facts.home else facts.home
    home_pct, away_pct = _model_pcts(facts)
    fav_pct, dog_pct = (home_pct, away_pct) if fav is facts.home else (away_pct, home_pct)
    fav_ref, dog_ref = _ref(fav, facts, rank=False), _ref(dog, facts, rank=False)
    if _variant(facts, 1):
        return f"Our model has {fav_ref} at {fav_pct}%, with {dog_ref} at {dog_pct}%."
    return f"Our model gives {fav_ref} {fav_pct}% and {dog_ref} {dog_pct}%."


def _market(facts: GameFacts) -> str | None:
    if facts.spread_home is None:
        return None
    pair = market_favorite(facts)
    if pair is None:
        return "The betting market calls it a pick'em."
    fav = pair[0]
    line = abs(facts.spread_home)
    favored = f"favored by {line:g} {'point' if line == 1 else 'points'}"
    fav_ref = _ref(fav, facts, rank=False)
    model_fav = _model_favorite(facts)
    if model_fav is not None and model_fav is not fav:
        return f"The betting market leans the other way, with {fav_ref} {favored}."
    if model_fav is not None and _variant(facts, 2):
        return f"The betting market agrees, with {fav_ref} {favored}."
    is_are = _verb(facts, "are", "is")
    return f"{_cap(fav_ref)} {is_are} {favored} in the betting market."


def _team_form(
    team: TeamFacts, other: TeamFacts, facts: GameFacts, detail: bool, when_last: str
) -> str:
    ref = _ref(team, facts, rank=False)
    if team.games_this_season == 0:
        return f"{ref} {_verb(facts, 'open their', 'opens its')} season here"
    text = f"{ref} {_verb(facts, 'are', 'is')} {team.record}"
    if not detail:
        return text
    if team.streak:
        return f"{text} and {_verb(facts, 'have', 'has')} {team.streak}"
    # A score that reads like either record would be claimed for the wrong team.
    records = (team.record, other.record)
    if team.last_game and not any(
        re.search(rf"(?<![\d-]){re.escape(r)}(?![\d-])", team.last_game) for r in records
    ):
        return f"{text} and {team.last_game} {when_last}"
    return text


def _form(facts: GameFacts, detail: bool) -> str:
    if facts.home.games_this_season == 0 and facts.away.games_this_season == 0:
        return "It is the season opener for both teams."
    first = _model_favorite(facts) or facts.home
    second = facts.away if first is facts.home else facts.home
    lead = _team_form(first, second, facts, detail, "last time out")
    last_game = _verb(facts, "in their last game", "in its last game")
    follow = _team_form(second, first, facts, detail, last_game)
    return f"{_cap(lead)}, while {follow}."


def _drafts(facts: GameFacts) -> list[str]:
    """Richest first; later drafts drop detail, then the venue, to stay short
    and plain. Dashes copied from a name become commas."""
    model, market = _model(facts), _market(facts)
    core = " ".join(s for s in (model, market) if s)
    drafts = [
        f"{_setting(facts, True)} {core} {_form(facts, True)}",
        f"{_setting(facts, True)} {core} {_form(facts, False)}",
        f"{_setting(facts, False)} {core} {_form(facts, False)}",
        f"{_setting(facts, False)} {core}",
        core,
        model,
    ]
    return [plain_punctuation(d) for d in drafts]


def fallback_reason(text: str, facts: GameFacts) -> str | None:
    """Why a fallback text cannot ship, or None."""
    if _UNSAFE_PUNCTUATION_RE.search(text):
        return "contains a semicolon or colon"
    return check_narration(text, facts)


def fallback_narration(facts: GameFacts) -> str:
    """The richest draft that fits the word budget and passes the fact check;
    the model sentence alone as the last resort."""
    drafts = _drafts(facts)
    for text in drafts:
        if len(text.split()) <= MAX_WORDS and fallback_reason(text, facts) is None:
            return text
    return drafts[-1]


def minimal_narration(home_abbr: str, away_abbr: str, home_win_prob: float) -> str:
    """One sentence from the prediction row alone: abbreviations and the
    model's whole-number percentages, nothing that needs the database."""
    for abbr in (home_abbr, away_abbr):
        if not isinstance(abbr, str) or not abbr.strip():
            raise ValueError("missing team abbreviation")
    home_pct, away_pct = round(home_win_prob * 100), round((1 - home_win_prob) * 100)
    if home_pct == 50:
        return f"Our model sees a coin flip between {home_abbr} and {away_abbr}."
    return f"Our model gives {home_abbr} {home_pct}% and {away_abbr} {away_pct}%."
