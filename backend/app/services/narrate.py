"""LLM narration of model output. The LLM never computes or alters the
probability: it previews a pre-game fact sheet, and every checkable claim it
makes is verified against that sheet. A failed narration never blocks a
prediction (returns None)."""

import logging
import re
import time
from dataclasses import dataclass, field

import anthropic

from app.config import get_settings
from app.services.fact_sheet import GameFacts, TeamFacts, market_favorite, render_fact_sheet

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MAX_WORDS = 90
TEMPERATURE = 0.8

SYSTEM_PROMPT = """You write the "From the booth" preview for one football game on Blitzcast, \
a site that shows a statistical model's win probability. You are a studio analyst on a big-game \
pregame show, talking at whip-around pace.

Shape, 2 to 4 sentences, at most 80 words:
1. Open with the storyline from the fact sheet: the stakes, the matchup, or a team's recent \
results. Never open with a percentage.
2. Give the model's pick and its percentage, once.
3. Back it with one or two reasons from the fact sheet: the betting market, recent results, \
the injury report, or the listed factors.
Short, punchy, present-tense sentences. Real football language. Scale the energy to the stakes: \
a ranked showdown or division game gets more juice than a mismatch.

Hard rules:
- Use only facts written in the fact sheet. Never mention a player, coach, stadium, city, \
ranking, record, score, streak, or history that is not written there.
- Write every number as digits. Percentages as digits with a % sign, like 62%.
- The betting market: the favored team is "favored by" or "laying" the points, the underdog is \
"getting" them. Use the exact line from the fact sheet. If it says no betting line is posted, \
do not mention Vegas, the line, the spread, or the market at all.
- The model and the market can disagree. Say so plainly when they do.
- If a factor says its window still includes last season's games, do not call it recent form.
- Never say Elo, EPA, SHAP, folks, locked, not even close, wire-to-wire, and company, or sitting \
pretty. Do not state the same idea twice.
- Commas and periods only. No em dashes, en dashes, semicolons, colons, lists, or headings. \
Hyphens inside scores like 24-17 are fine.
- No betting advice."""

CFB_INJURY_GUARDRAIL = (
    "\n- College football has no reliable injury report. Never mention player availability "
    "or injuries."
)

EXAMPLES = """Example fact sheet:
Sport: NFL
Matchup: Steelers at Browns
When: Thursday night
Game type: AFC North division game
Model: Steelers 62% to win, Browns 38%
Betting market: Steelers favored by 2.5 points (PIT -2.5, CLE +2.5). Total 38.5.
Last meeting: Browns won 13-6 in Week 17 of 2025
Pittsburgh Steelers (PIT): record 2-1, last game beat the Bengals 30-27 at home, \
rest on a short week
Cleveland Browns (CLE): record 2-1, last game beat the Panthers 21-18 on the road, \
streak won 2 straight

Example narration:
Thursday night in Cleveland, and the AFC North gets its first rematch on a short week. Pittsburgh \
bounced back by edging Cincinnati 30-27, while the Browns have won 2 straight. Our model likes \
the Steelers at 62%, a touch more confident than a market laying 2.5 points on the road.

Example narration for a mismatch:
Ohio State opens Big Ten play riding a 4-0 start, and nobody needs a film session for this one. \
The Buckeyes are 40.5-point favorites, and our model puts them at 98%."""

_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    "fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    "eighty|ninety|hundred"
)
_SPELLED_NUMBER_RE = re.compile(
    rf"\b(?:{_NUMBER_WORDS})\b[\w\s-]{{0,20}}?\b(?:percent|points?)\b", re.IGNORECASE
)
_DASH_RE = re.compile(r"\s*[—–]\s*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_NAME_WORD_RE = re.compile(r"[A-Za-z']+")
_CAP_RE = re.compile(r"\b[A-Z][A-Za-z0-9'’&.]*")
_FAVORITE_RE = re.compile(r"favorite|favored|the edge|an edge|the nod")
_LAYING_RE = re.compile(r"\blaying\b|\bgiving\b")
_GETTING_RE = re.compile(r"\bgetting\s+(?:\d|a\b)|\+\s?\d")
_MARKET_RE = re.compile(
    r"vegas|the line\b|spread|the market|betting|oddsmaker|sportsbook|\bbooks?\b|"
    r"\blaying\b|favored by|getting \d|\+\s?\d"
)
_POINTS_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)[\s-]*points?\b")

# Word-bounded so "epa" never matches inside "prepared" or "separates".
_BANNED_RE = re.compile(
    r"\b(folks|locked|not even close|wire[- ]to[- ]wire|and company|sitting pretty|elo|epa|shap)\b",
    re.IGNORECASE,
)

# Generic capitalized words (sentence starts, calendar words, football terms).
# Only add plain English words here, never names.
COMMON_CAPITALIZED = {
    "a", "an", "the", "and", "but", "or", "so", "if", "when", "while", "with", "this", "that",
    "these", "those", "they", "their", "it", "it's", "its", "he", "she", "we", "our", "you",
    "your", "i", "i'll", "i'd", "there", "here", "now", "still", "even", "just", "only", "both",
    "after", "before", "back", "meanwhile", "expect", "look", "don't", "can't", "won't",
    "nobody", "everyone", "one", "two", "three", "four", "five", "first", "last", "next",
    "no", "yes", "not", "all", "every", "for", "from", "in", "on", "at", "by", "to", "of",
    "as", "up", "out", "down", "over", "under", "behind", "between", "against", "despite",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "september", "october", "november", "december", "january", "february",
    "week", "vegas", "ap", "fbs", "fcs", "nfl", "cfb", "afc", "nfc", "model",
    "game", "kickoff", "football", "college", "pro", "home", "road", "defense", "offense",
    "big", "top", "ranked", "unranked", "number", "no.", "neutral", "sunday's", "saturday's",
}


@dataclass
class NarrationResult:
    text: str | None
    attempts: int
    rejections: list[str] = field(default_factory=list)


def _system_prompt(sport: str) -> str:
    rules = SYSTEM_PROMPT + (CFB_INJURY_GUARDRAIL if sport == "CFB" else "")
    return f"{rules}\n\n{EXAMPLES}"


def _user_content(facts: GameFacts) -> str:
    return (
        "Fact sheet:\n"
        f"{render_fact_sheet(facts)}\n\n"
        "Write the From the booth preview for this game."
    )


def _plain_punctuation(text: str) -> str:
    """Broadcast copy reads as commas and periods; models drift to em dashes."""
    text = _DASH_RE.sub(", ", text)
    text = re.sub(r",\s*,", ",", text)
    return re.sub(r"\s+([,.!?])", r"\1", text)


def _name_tokens(text: str) -> set[str]:
    tokens = set()
    for match in _CAP_RE.finditer(text):
        token = match.group(0).rstrip(".").lower()
        tokens.add(re.sub(r"['’]s$", "", token))
    return tokens


def _team_positions(sentence_low: str, team: TeamFacts) -> list[int]:
    abbr = rf"\b{re.escape(team.abbr.lower())}\b"
    positions = [m.start() for m in re.finditer(abbr, sentence_low)]
    words = _NAME_WORD_RE.findall(f"{team.full_name} {team.mascot or ''}")
    for word in {w for w in words if len(w) > 3}:
        positions += [m.start() for m in re.finditer(re.escape(word.lower()), sentence_low)]
    return positions


def _attribution_ok(
    sentence_low: str, pattern: re.Pattern, expected: TeamFacts, other: TeamFacts
) -> bool:
    """Each keyword's nearest preceding team mention must be `expected`."""
    exp, oth = _team_positions(sentence_low, expected), _team_positions(sentence_low, other)
    for m in pattern.finditer(sentence_low):
        nearest_exp = max((p for p in exp if p < m.start()), default=-1)
        nearest_oth = max((p for p in oth if p < m.start()), default=-1)
        if nearest_oth > nearest_exp:
            return False
    return True


def _market_reason(market_sentences: list[str], facts: GameFacts) -> str | None:
    if facts.spread_home is None:
        return "mentions a betting market but no line exists" if market_sentences else None
    pair = market_favorite(facts)
    if pair is None:
        return None
    fav, dog = pair
    line = abs(facts.spread_home)
    allowed = {line} | ({facts.total} if facts.total is not None else set())
    for s in market_sentences:
        favorite_ok = _attribution_ok(s, _FAVORITE_RE, fav, dog)
        if not (favorite_ok and _attribution_ok(s, _LAYING_RE, fav, dog)):
            return f"says the wrong team is the betting favorite (the market favors {fav.name})"
        if not _attribution_ok(s, _GETTING_RE, dog, fav):
            return f"says the favorite is getting points (only {dog.name} is getting points)"
        for m in _POINTS_NUM_RE.finditer(s):
            if float(m.group(1)) not in allowed:
                return f"cites {m.group(1)} points but the line is {line:g}"
    return None


def check_narration(text: str, facts: GameFacts) -> str | None:
    """Return why `text` breaks a rule, or None when every check passes."""
    if not text:
        return "empty response"
    words = len(text.split())
    if words > MAX_WORDS:
        return f"too long ({words} words, limit {MAX_WORDS})"
    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    if len(sentences) > 4:
        return "more than 4 sentences"
    banned = _BANNED_RE.search(text)
    if banned:
        return f"uses banned phrase '{banned.group(1).lower()}'"
    if _SPELLED_NUMBER_RE.search(text):
        return "spells out a number, write digits"
    p = facts.home_win_prob
    valid = {round(p * 100), round((1 - p) * 100)}
    for match in _PCT_RE.finditer(text):
        if not any(abs(float(match.group(1)) - v) <= 1.0 for v in valid):
            return f"cites a percentage ({match.group(1)}%) the model did not produce"
    unknown = _name_tokens(text) - _name_tokens(render_fact_sheet(facts)) - COMMON_CAPITALIZED
    if unknown:
        return f"names not in the fact sheet: {', '.join(sorted(unknown))}"
    lowered = [s.lower() for s in sentences]
    market = [s for s in lowered if _MARKET_RE.search(s)]
    reason = _market_reason(market, facts)
    if reason:
        return reason
    if p != 0.5:
        fav, dog = (facts.home, facts.away) if p > 0.5 else (facts.away, facts.home)
        for s in lowered:
            if s not in market and not _attribution_ok(s, _FAVORITE_RE, fav, dog):
                return f"calls the wrong team the model's favorite (the model favors {fav.name})"
    return None


def _call_api(client, model: str, system: str, messages: list[dict]) -> str:
    response = client.messages.create(
        model=model, max_tokens=300, temperature=TEMPERATURE, system=system, messages=messages
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return _plain_punctuation(text.strip().strip("*_#`").strip())


def generate(facts: GameFacts) -> NarrationResult:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not set; skipping narration")
        return NarrationResult(text=None, attempts=0)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system = _system_prompt(facts.sport)
    first = {"role": "user", "content": _user_content(facts)}
    messages = [first]
    rejections: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = _call_api(client, settings.anthropic_model, system, messages)
        except Exception as exc:
            logger.warning("narration attempt %d failed: %s", attempt, exc)
            rejections.append(f"api error: {exc}")
            time.sleep(2)
            continue
        reason = check_narration(text, facts)
        if reason is None:
            return NarrationResult(text=text, attempts=attempt, rejections=rejections)
        logger.warning("narration attempt %d rejected: %s", attempt, reason)
        rejections.append(reason)
        messages = [
            first,
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": f"That draft breaks a rule: {reason}. Rewrite it following every rule.",
            },
        ]
    return NarrationResult(text=None, attempts=MAX_ATTEMPTS, rejections=rejections)


def narrate(facts: GameFacts) -> str | None:
    return generate(facts).text
