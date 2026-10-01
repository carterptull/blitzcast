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


def _example_team(name: str, full_name: str, abbr: str, record: str, **kw) -> TeamFacts:
    base = dict(
        name=name, full_name=full_name, abbr=abbr, mascot=kw.pop("mascot", name), record=record,
        games_this_season=sum(int(n) for n in record.split("-")),
        last_game=None, streak=None, scoring=None, rank=None, rank_note=None, rest=None,
        injuries=(),
    )
    return TeamFacts(**(base | kw))


# The examples are rendered from real GameFacts so they always match the sheet
# format, and tests run the example narrations through check_narration.
EXAMPLE_FACTS = GameFacts(
    sport="NFL",
    home=_example_team(
        "Browns", "Cleveland Browns", "CLE", "2-1",
        last_game="beat the Panthers 21-18 on the road", streak="won 2 straight",
    ),
    away=_example_team(
        "Steelers", "Pittsburgh Steelers", "PIT", "2-1",
        last_game="beat the Bengals 30-27 at home", rest="on a short week",
    ),
    home_win_prob=0.38, spread_home=-2.5, total=38.5, when="Thursday night", venue=None,
    is_neutral_site=False, matchup_note="AFC North division game",
    last_meeting="Browns won 13-6 in Week 17 of 2025", weather=None, factor_lines=(),
)
EXAMPLE_NARRATION = (
    "Thursday night in the AFC North, and the Steelers come in on a short week. Pittsburgh "
    "edged the Bengals 30-27 at home, while the Browns have won 2 straight. Our model likes "
    "the Steelers at 62%, a touch more confident than a market laying 2.5 points on the road."
)
MISMATCH_EXAMPLE_FACTS = GameFacts(
    sport="CFB",
    home=_example_team(
        "Ohio State", "Ohio State Buckeyes", "OSU", "4-0",
        mascot="Buckeyes", streak="won 4 straight",
    ),
    away=_example_team("Purdue", "Purdue Boilermakers", "PUR", "1-3", mascot="Boilermakers"),
    home_win_prob=0.98, spread_home=40.5, total=None, when="Saturday afternoon", venue=None,
    is_neutral_site=False, matchup_note="Big Ten conference game", last_meeting=None,
    weather=None, factor_lines=(),
)
MISMATCH_EXAMPLE_NARRATION = (
    "Ohio State brings a 4-0 start into a Big Ten conference game, and nobody needs a film "
    "session for this one. The Buckeyes are 40.5-point favorites, and our model puts them at 98%."
)
EXAMPLES = (
    f"Example fact sheet:\n{render_fact_sheet(EXAMPLE_FACTS)}\n\n"
    f"Example narration:\n{EXAMPLE_NARRATION}\n\n"
    f"Example fact sheet for a mismatch:\n{render_fact_sheet(MISMATCH_EXAMPLE_FACTS)}\n\n"
    f"Example narration for a mismatch:\n{MISMATCH_EXAMPLE_NARRATION}"
)

_NUM = r"\d+(?:\.\d+)?"
_NOT_PCT = r"(?!\d+(?:\.\d+)?\s*(?:%|percent|per\s+cent))"
_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)", re.IGNORECASE)
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    "fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    "eighty|ninety|hundred"
)
_NUMBER_WORDS_NO_ONE = _NUMBER_WORDS.replace("one|", "")
# "One of the" is a pronoun, so "one" is only rejected next to a unit.
_SPELLED_NUMBER_RE = re.compile(
    rf"\b(?:{_NUMBER_WORDS})(?:[\s-]+(?:{_NUMBER_WORDS}))*[\s-]+"
    r"(?:points?|percent|per\s+cent|yards?)\b"
    rf"|\b(?:{_NUMBER_WORDS_NO_ONE})(?:[\s-]+(?:{_NUMBER_WORDS}))*[\s-]+(?:games?|straight|times)\b"
    rf"|\b(?:by|plus|minus)\s+(?:{_NUMBER_WORDS})\b(?!\s+of\b)"
    rf"|\b(?:laying|giving|getting)\s+(?:{_NUMBER_WORDS_NO_ONE})\b"
    r"|\ba\s+(?:point|field\s+goal)\s+and\s+a\s+half\b|\bhalf\s+a\s+point\b",
    re.IGNORECASE,
)
_DASH_RE = re.compile(r"\s*[—–]\s*")
# Never split after "vs.", "No.", "St.", titles, or initials like "T.J.".
_SENTENCE_RE = re.compile(
    r"(?<=[.!?])(?<!\bvs\.)(?<!\bVs\.)(?<!\bNo\.)(?<!\bSt\.)(?<!\bMt\.)(?<!\bJr\.)(?<!\bSr\.)"
    r"(?<!\bDr\.)(?<!\b[A-Z]\.)\s+"
)
_CLAUSE_BREAK_RE = re.compile(
    r";|,\s+(?:and|so)\s+|\s+(?:but|while|whereas|though|although|yet|despite|"
    r"even\s+(?:with|as|if|though))\s+",
    re.IGNORECASE,
)
_NAME_WORD_RE = re.compile(r"[A-Za-z0-9&']+")
_CAP_RE = re.compile(r"\b[A-Z][A-Za-z0-9'’&.]*")
_LOWER_WORD_RE = re.compile(r"\b[a-z][a-z'’]*")
# A trailing period or comma still ends the token ("went 5-0." is checked).
_SCORE_RE = re.compile(r"(?<![\w.-])\d{1,3}-\d{1,3}(?:-\d{1,3})?(?![\w-]|\.\d)")
_RANK_RE = re.compile(r"(?:\bNo\.\s?|#|\bnumber\s+)(\d{1,3})(?![\w-]|\.\d)", re.IGNORECASE)
_STREAK_RE = re.compile(r"(?:\b(?:won|lost)\s+)?\b\d{1,2}\s+straight\b", re.IGNORECASE)
_MODEL_RE = re.compile(r"\bmodel(?:['’]s)?\b", re.IGNORECASE)
_CONTRAST_RE = re.compile(
    r"\b(?:but|while|whereas|though|although|yet|despite)\b", re.IGNORECASE
)

# Market words. A sentence with any of these is a market sentence.
_AMOUNT = (
    rf"(?:just\s+|only\s+)?(?:{_NOT_PCT}\d|the\s+points|points|a\s+point|a\s+field\s+goal|"
    r"a\s+touchdown)"
)
_LAYING = rf"\b(?:laying|lays|giving|gives)\s+{_AMOUNT}|\bminus\s+{_NOT_PCT}\d|(?<![\w.%])-\s?\d"
_GETTING = rf"\b(?:getting|gets)\s+{_AMOUNT}|\bplus\s+{_NOT_PCT}\d|(?<![\w.%])\+\s?\d"
_N_POINT = rf"{_NUM}[\s-]+points?\s+(?:\w+\s+)?(?:favou?rites?|underdogs?|dogs?)\b"
_FAVORED_BY = r"\bfavou?red\s+by\s+(?:just\s+|only\s+)?\d"
_LAYING_RE = re.compile(_LAYING, re.IGNORECASE)
_GETTING_RE = re.compile(_GETTING, re.IGNORECASE)
_MARKET_RE = re.compile(
    r"\bvegas\b|\bthe\s+line\b(?!\s+of\s+scrimmage)|\bspreads?\b|\bthe\s+market\b|\bbetting\b"
    r"|\boddsmakers?\b|\bsportsbooks?\b|(?<!record\s)\bbooks\b|\bpick\s?['’]?\s?em\b"
    r"|\bmoneyline\b|\bover/under\b|\btotal\s+(?:of|at|is|sits|set)\b"
    rf"|{_FAVORED_BY}|{_LAYING}|{_GETTING}|{_N_POINT}",
    re.IGNORECASE,
)
_FAV_RE = re.compile(r"\bfavou?r(?:ed|ites?)\b|\b(?:the|an)\s+edge\b|\bthe\s+nod\b", re.IGNORECASE)
_DOG_RE = re.compile(
    r"\bunderdogs?\b|\b(?:the|a|an)\s+(?:road\s+|home\s+)?dogs?\b", re.IGNORECASE
)
# "Vegas likes X" / "our model leans X": the team is the object after the verb.
_AGENT_RE = re.compile(
    r"\b(model|vegas|market|books|oddsmakers|sportsbooks?|line)(?:['’]s)?\s+(?:\w+\s+)?"
    r"(?:likes|leans|backs|favors|favours|prefers|loves|trusts|sides\s+with|is\s+on)\b",
    re.IGNORECASE,
)
_LINE_NUM_RE = re.compile(
    rf"\bfavou?red\s+by\s+(?:just\s+|only\s+)?({_NUM})"
    rf"|\b(?:laying|lays|giving|gives|getting|gets|plus|minus)\s+(?:just\s+|only\s+)?"
    rf"{_NOT_PCT}({_NUM})"
    rf"|(?<![\w.%])[+-]\s?({_NUM})"
    rf"|({_NUM})[\s-]+points?\s+(?:\w+\s+)?(?:favou?rites?|underdogs?|dogs?)\b"
    rf"|\b(?:spread|line)\s+(?:of|at|is)\s+(?:just\s+|only\s+)?({_NUM})",
    re.IGNORECASE,
)
_TOTAL_NUM_RE = re.compile(
    rf"\b(?:total|over/under)\s+(?:of\s+|at\s+|is\s+|sits\s+at\s+|set\s+at\s+)?({_NUM})",
    re.IGNORECASE,
)
_MARKET_ONLY_FAV_RE = re.compile(rf"{_FAVORED_BY}|{_N_POINT}", re.IGNORECASE)
_PAIRED_PCT_RE = re.compile(r"\s*(?:to|vs\.?|versus|over|against|-)\s*", re.IGNORECASE)
_AS_ROLE_RE = re.compile(r"\bas\s+(?:an?\s+|the\s+)?(?:[\w.'’-]+\s+){0,2}$", re.IGNORECASE)
_FOR_RE = re.compile(r"\s+for\s+(?:the\s+)?", re.IGNORECASE)
_CFB_INJURY_RE = re.compile(
    r"\binjur|\bout\s+for\b|\bmissing\b|\bsidelined\b|\bquestionable\b|\bdoubtful\b"
    r"|\bruled\s+out\b",
    re.IGNORECASE,
)
# Explicit injury attribution: "Baltimore's Joe Burrow", "Ravens quarterback Joe
# Burrow", "the Ravens are without Joe Burrow", "Joe Burrow is out for the Ravens".
_PLAYER_ROLE = (
    r"(?:(?:star|starting|veteran|rookie|backup|top)\s+)?"
    r"(?:quarterback|qb|signal[\s-]caller|wide\s+receiver|receiver|wideout|wr|running\s+back"
    r"|rb|tight\s+end|te|tackle|guard|center|linebacker|lb|cornerback|cb|safety|pass\s+rusher"
    r"|edge\s+rusher|kicker)\s+"
)
_TEAM_TO_PLAYER = (
    rf"(?:['’]s?\s+(?:{_PLAYER_ROLE})?|\s+{_PLAYER_ROLE}"
    r"|\s+(?:is|are|was|were|will\s+be)\s+(?:still\s+|again\s+)?(?:playing\s+)?without\s+"
    rf"(?:{_PLAYER_ROLE})?)"
)
_PLAYER_TO_TEAM = (
    r"(?:\s*\([A-Za-z]{1,4}\))?,?\s+(?:is\s+|was\s+|remains\s+|will\s+be\s+)?"
    r"(?:listed\s+|ruled\s+)?(?:as\s+)?"
    r"(?:out|doubtful|questionable|inactive|sidelined|unavailable|injured)\s+for\s+(?:the\s+)?"
)

# Word-bounded so "epa" never matches inside "prepared" or "separates".
_BANNED_RE = re.compile(
    r"\b(folks|locked|not even close|wire[- ]to[- ]wire|and company|sitting pretty|elo|epa|shap)\b",
    re.IGNORECASE,
)

# Name words that never identify one team on their own.
_GENERIC_NAME_WORDS = {
    "state", "university", "college", "north", "south", "east", "west", "central",
    "northern", "southern", "eastern", "western",
}

# Generic capitalized words (sentence openers, calendar words, football terms).
# Only add plain English words here, never names or surname-like words
# (Love, Brown, Allen, Hill, Young, Chase, Hurts, Swift, ...).
COMMON_CAPITALIZED = {
    # Articles, pronouns, determiners.
    "a", "an", "the", "this", "that", "these", "those", "it", "it's", "its", "they",
    "they're", "their", "them", "he", "she", "we", "we're", "our", "you", "you're", "your",
    "i", "i'm", "i'll", "i'd", "there", "there's", "here", "here's", "what", "what's", "who",
    "which", "why", "how", "where", "everyone", "everybody", "nobody", "somebody", "anyone",
    "something", "nothing", "everything", "neither", "either", "each", "every", "another",
    "other", "both", "all", "any", "some", "many", "most", "few", "several", "much", "more",
    "less", "such", "one", "two", "three", "four", "five", "ten",
    # Conjunctions and adverbs.
    "and", "but", "or", "nor", "so", "yet", "if", "when", "while", "whereas", "though",
    "although", "because", "since", "unless", "until", "as", "than", "then", "now", "still",
    "even", "just", "only", "also", "too", "again", "once", "already", "almost", "never",
    "always", "often", "maybe", "perhaps", "however", "meanwhile", "instead", "otherwise",
    "plus", "not", "no", "yes", "sure", "indeed", "really", "simply", "tonight", "today",
    "tomorrow", "first", "second", "third", "fourth", "last", "next", "finally",
    # Prepositions.
    "for", "from", "in", "on", "at", "by", "to", "of", "up", "out", "down", "over", "under",
    "behind", "between", "against", "despite", "after", "before", "back", "into", "off",
    "around", "through", "across", "with", "without", "inside", "outside", "beyond", "past",
    "toward", "about", "above", "below",
    # Verbs that open a sentence.
    "expect", "look", "forget", "make", "call", "coming", "going", "getting", "taking",
    "bring", "give", "take", "keep", "watch", "picture", "imagine", "think", "believe",
    "consider", "remember", "let's", "don't", "can't", "won't", "isn't", "aren't", "doesn't",
    "didn't", "wasn't", "is", "are", "was", "were", "be", "has", "have", "had", "do", "does",
    "did", "can", "could", "should", "would", "will", "must", "might", "get", "go", "buckle",
    "strap", "hold", "enter", "welcome", "say", "know", "bet",
    # Calendar.
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
    # Football words and acronyms.
    "week", "weekend", "vegas", "ap", "fbs", "fcs", "nfl", "cfb", "afc", "nfc", "model",
    "game", "games", "kickoff", "football", "college", "pro", "home", "road", "defense",
    "offense", "quarterback", "coach", "rivalry", "showdown", "heavyweight", "primetime",
    "prime", "time", "night", "morning", "afternoon", "evening", "season", "postseason",
    "playoff", "conference", "division", "title", "fight", "matchup", "rematch", "upset",
    "trap", "underdog", "underdogs", "favorite", "favorites", "edge", "line", "spread",
    "total", "market", "stakes", "crowd", "stadium", "start", "streak", "record", "bye",
    "rest", "big", "top", "ranked", "unranked", "number", "neutral", "site", "points", "point",
    "yards", "pickup", "touchdown", "touchdowns", "turnover", "turnovers", "injury",
    "injuries", "report", "availability", "scoring", "passing", "rushing", "running",
    "attack", "secondary", "backfield", "trenches", "tempo", "possession", "drive", "drives",
    "margin", "differential", "form", "pick", "picks", "odds", "win", "wins", "winning",
    "loss", "losses", "losing", "lead", "winners", "visitors", "hosts", "guests", "rivals",
    "battle", "clash", "test", "chance", "chances", "opportunity", "redemption", "pride",
    # Weather.
    "weather", "cold", "snow", "snowy", "rain", "rainy", "heat", "wind", "windy", "humid",
    "humidity", "hot", "warm", "chilly", "freezing", "sunny", "degrees", "conditions",
    "dome", "indoors", "outdoors", "lights",
    # Stakes and storylines.
    "revenge", "statement", "momentum", "pressure", "history", "spotlight", "survival",
    "measuring",
    # Plain adjectives that open a sentence.
    "huge", "massive", "enormous", "bad", "good", "great", "short", "long", "unbeaten",
    "undefeated", "winless", "perfect", "clean", "tough", "early", "late", "quick", "fast",
    "slow", "real", "true", "wild", "loud", "ugly", "rough", "healthy", "rested", "fresh",
    "tired", "desperate", "dangerous", "elite", "solid", "steady", "different", "same",
    "new", "old", "high", "low", "full", "easy", "hard", "close", "tight", "slight", "small",
    "major", "key", "critical", "crucial", "brutal", "nasty", "gritty", "physical",
    "explosive", "balanced", "dominant", "impressive", "marquee", "signature",
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


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_RE.split(text) if s.strip()]


def _name_tokens(text: str) -> set[str]:
    tokens = set()
    for match in _CAP_RE.finditer(text):
        token = match.group(0).rstrip(".").lower()
        tokens.add(re.sub(r"['’]s$|['’]$", "", token))
    return tokens


def _team(facts: GameFacts, side: str) -> TeamFacts:
    return facts.home if side == "home" else facts.away


def _other(side: str) -> str:
    return "away" if side == "home" else "home"


def _name_words(team: TeamFacts) -> set[str]:
    text = f"{team.full_name} {team.name} {team.mascot or ''}"
    return {w.lower() for w in _NAME_WORD_RE.findall(text)}


# Role phrases name a side outright, except at a neutral site.
_ROLE_ALIASES = {
    "away": ("the visitors", "the visiting team", "the road team", "the away team", "the guests"),
    "home": ("the home team", "the hosts", "the host"),
}


def _aliases(facts: GameFacts) -> list[tuple[str, str | None, bool]]:
    """(alias, side, case_sensitive), longest first. Aliases are the full name,
    short name, mascot, abbreviation, name words unique to one team, and role
    phrases like "the visitors". A side of None masks venue text so
    "DKR-Texas Memorial Stadium" is not Texas."""
    names = {}
    for side in ("home", "away"):
        team, other = _team(facts, side), _team(facts, _other(side))
        own = {team.full_name, team.name, team.mascot or "", f"{team.name} {team.mascot or ''}"}
        unique = _name_words(team) - _name_words(other) - _GENERIC_NAME_WORDS
        own |= {w for w in unique if len(w) > 3}
        names[side] = {n.strip().lower() for n in own if n.strip()}
    shared = names["home"] & names["away"]
    aliases = [(a, side, False) for side in names for a in names[side] - shared]
    if facts.home.abbr != facts.away.abbr:
        aliases += [(_team(facts, s).abbr, s, True) for s in ("home", "away")]
    if facts.venue:
        venue_names = {facts.venue, facts.venue.split(" in ")[0]}
        aliases += [(v.lower(), None, False) for v in venue_names]
    if not facts.is_neutral_site:
        aliases += [(r, side, False) for side, roles in _ROLE_ALIASES.items() for r in roles]
    return sorted(aliases, key=lambda a: -len(a[0]))


def _mentions(sentence: str, facts: GameFacts) -> list[tuple[int, int, str]]:
    """Team mentions as (start, end, side). Longest alias wins and masks its
    span, so "Kansas State" is never also read as "Kansas". Abbreviations are
    matched case-sensitively so "NO" (Saints) never matches the word "no"."""
    taken, found = [], []
    for alias, side, case_sensitive in _aliases(facts):
        flags = 0 if case_sensitive else re.IGNORECASE
        for m in re.finditer(rf"(?<![\w&]){re.escape(alias)}(?![\w&])", sentence, flags):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            taken.append(m.span())
            if side:
                found.append((m.start(), m.end(), side))
    return sorted(found)


@dataclass
class _Sentence:
    """One sentence with its team mentions and clause spans. Clauses split on
    "but", "while", ", and" and similar, so a market clause and a model clause
    in one sentence are judged separately. Pronouns are not resolved: a claim
    with no team in its clause falls back to the sentence's first team mention."""

    text: str
    mentions: list[tuple[int, int, str]]
    clauses: list[tuple[int, int]]

    @classmethod
    def parse(cls, text: str, facts: GameFacts) -> "_Sentence":
        clauses, start = [], 0
        for m in _CLAUSE_BREAK_RE.finditer(text):
            clauses.append((start, m.start()))
            start = m.end()
        clauses.append((start, len(text)))
        return cls(text, _mentions(text, facts), clauses)

    def clause(self, pos: int) -> tuple[int, int]:
        return next((c for c in self.clauses if pos < c[1]), self.clauses[-1])

    def in_model_clause(self, pos: int) -> bool:
        start, end = self.clause(pos)
        return bool(_MODEL_RE.search(self.text[start:end]))

    def is_market(self) -> bool:
        if _MARKET_RE.search(self.text):
            return True
        return any(not self.in_model_clause(m.start()) for m in _DOG_RE.finditer(self.text))

    def side_at(self, start: int, end: int, prefer_after: bool = False) -> str | None:
        cs, ce = self.clause(start)
        before = [m for m in self.mentions if m[0] >= cs and m[1] <= start]
        if before and _AS_ROLE_RE.search(self.text[cs:start]):
            # "The Chargers host the Rams as 2.5-point favorites": the subject.
            return before[0][2]
        after = [m for m in self.mentions if m[0] >= end and m[1] <= ce]
        for pick in ((after[:1], before[-1:]) if prefer_after else (before[-1:], after[:1])):
            if pick:
                return pick[0][2]
        return self.mentions[0][2] if self.mentions else None

    def side_starting_at(self, pos: int) -> str | None:
        return next((m[2] for m in self.mentions if m[0] == pos), None)


def _percentage_reason(s: _Sentence, facts: GameFacts) -> str | None:
    """Each percentage belongs to the team named nearest before it in its
    clause (else after it). "55% to 45%" gives the second number to the other
    team, and "55% for Ohio State" to the team after "for"."""
    prev: tuple[int, str] | None = None
    for m in _PCT_RE.finditer(s.text):
        side = None
        if prev and _PAIRED_PCT_RE.fullmatch(s.text[prev[0]:m.start()]):
            side = _other(prev[1])
        else:
            follow = _FOR_RE.match(s.text, m.end())
            side = (follow and s.side_starting_at(follow.end())) or s.side_at(m.start(), m.end())
        prev = (m.end(), side) if side else None
        if side is None:
            continue
        team = _team(facts, side)
        p = facts.home_win_prob if side == "home" else 1 - facts.home_win_prob
        expected = round(p * 100)
        if abs(float(m.group(1)) - expected) > 1.0:
            return (
                f"gives {team.name} {m.group(1)}% but the model has {team.name} at {expected}%"
            )
    return None


def _market_claim_reason(side: str, role: str, facts: GameFacts) -> str | None:
    if facts.spread_home is None:
        return "mentions a betting market but no line exists"
    pair = market_favorite(facts)
    if pair is None:
        return "calls a team the betting favorite or underdog but the line is a pick'em"
    fav, dog = pair
    team = _team(facts, side)
    if role == "favorite" and team is not fav:
        return f"says the wrong team is the betting favorite (the market favors {fav.name})"
    if role == "getting" and team is not dog:
        return f"says the favorite is getting points (only {dog.name} is getting points)"
    if role == "underdog" and team is not dog:
        return f"calls the betting favorite the underdog (the market favors {fav.name})"
    return None


def _model_claim_reason(side: str, role: str, facts: GameFacts) -> str | None:
    p = facts.home_win_prob
    if p == 0.5:
        return None
    fav_side = "home" if p > 0.5 else "away"
    fav = _team(facts, fav_side)
    if role == "favorite" and side != fav_side:
        return f"calls the wrong team the model's favorite (the model favors {fav.name})"
    if role != "favorite" and side == fav_side:
        return f"calls the model's favorite the underdog (the model favors {fav.name})"
    return None


def _contrasted_with_model(s: _Sentence, pos: int) -> bool:
    """"The Longhorns are favored, but our model gives the Buckeyes 55%": a bare
    favorite clause set against a model clause is the market's view. A clause
    with a percentage is still read as the model's."""
    start, end = s.clause(pos)
    return (
        bool(_CONTRAST_RE.search(s.text)) and bool(_MODEL_RE.search(s.text))
        and not _PCT_RE.search(s.text[start:end])
    )


def _claims_reason(s: _Sentence, facts: GameFacts, market: bool) -> str | None:
    """Favorite / underdog wording is a market claim in a market sentence and a
    model claim otherwise, except in a clause that names the model. Laying,
    getting, signed numbers, "favored by N" and "N-point favorite" are always
    market claims."""
    claims = [(m, "favorite", False) for m in _FAV_RE.finditer(s.text)]
    claims += [(m, "underdog", False) for m in _DOG_RE.finditer(s.text)]
    claims += [(m, "favorite", True) for m in _LAYING_RE.finditer(s.text)]
    claims += [(m, "getting", True) for m in _GETTING_RE.finditer(s.text)]
    for m, role, market_only in sorted(claims, key=lambda c: c[0].start()):
        side = s.side_at(m.start(), m.end())
        if side is None:
            continue
        window = s.text[max(0, m.start() - 25):m.end() + 15]
        market_only = market_only or bool(_MARKET_ONLY_FAV_RE.search(window))
        as_market = market or _contrasted_with_model(s, m.start())
        if market_only or (as_market and not s.in_model_clause(m.start())):
            reason = _market_claim_reason(side, role, facts)
        else:
            reason = _model_claim_reason(side, role, facts)
        if reason:
            return reason
    for m in _AGENT_RE.finditer(s.text):
        side = s.side_at(m.start(), m.end(), prefer_after=True)
        if side is None:
            continue
        if m.group(1).lower() == "model":
            reason = _model_claim_reason(side, "favorite", facts)
        else:
            reason = _market_claim_reason(side, "favorite", facts)
        if reason:
            return reason
    return None


def _market_numbers_reason(s: _Sentence, facts: GameFacts) -> str | None:
    """Only numbers attached to market words count, so a score margin like
    "won by 21 points" in a market sentence is not read as the line."""
    line = abs(facts.spread_home or 0.0)
    for m in _LINE_NUM_RE.finditer(s.text):
        number = next(g for g in m.groups() if g)
        if float(number) != line:
            return f"cites {number} points but the line is {line:g}"
    for m in _TOTAL_NUM_RE.finditer(s.text):
        if facts.total is None:
            return "cites a total but none is posted"
        if float(m.group(1)) != facts.total:
            return f"cites a total of {m.group(1)} but the total is {facts.total:g}"
    return None


def _injury_team_reason(s: _Sentence, facts: GameFacts) -> str | None:
    """An injury-report name must not be pinned on the other team. Only explicit
    attribution counts: "<team> is without <name>", "<team>'s <name>", "<team>
    quarterback <name>", and "<name> is listed Out for <team>". Co-occurrence
    ("Big edge for the Ravens with Joe Burrow out") is not checked. Only the
    full name is matched, and the listed status (Out vs Doubtful) is not checked."""
    for side in ("home", "away"):
        team, other = _team(facts, side), _other(side)
        for injury in team.injuries:
            name = injury.split(" (")[0].split(" is listed")[0]
            if name not in s.text:
                continue
            reason = f"puts {name} on the wrong team (the {team.name} list {name})"
            owned = re.compile(rf"{_TEAM_TO_PLAYER}{re.escape(name)}\b", re.IGNORECASE)
            if any(owned.match(s.text, m[1]) for m in s.mentions if m[2] == other):
                return reason
            for m in re.finditer(rf"{re.escape(name)}{_PLAYER_TO_TEAM}", s.text, re.IGNORECASE):
                if s.side_starting_at(m.end()) == other:
                    return reason
    return None


def _numeric_facts_reason(text: str, sheet: str) -> str | None:
    """Scores and records (24-17, 2-1-1), ranks (No. 3, #3) and streaks (won 4
    straight) must appear verbatim in the fact sheet. Lines and totals are
    checked by the market logic; years and Week N are never matched. Which team
    a number belongs to, and invented history with no number ("haven't lost at
    home all season"), are not checked."""
    sheet = " ".join(sheet.split())
    for m in _SCORE_RE.finditer(text):
        if not re.search(rf"(?<![\w.-]){re.escape(m.group(0))}(?![\w-]|\.\d)", sheet):
            return f"cites {m.group(0)} but the fact sheet has no such score or record"
    for m in _RANK_RE.finditer(text):
        if not re.search(rf"#{m.group(1)}(?!\d)", sheet):
            return f"cites {m.group(0)} but the fact sheet has no such rank"
    for m in _STREAK_RE.finditer(text):
        if m.group(0).lower() not in sheet.lower():
            return f"cites {m.group(0)} but the fact sheet has no such streak"
    return None


def check_narration(text: str, facts: GameFacts) -> str | None:
    """Return why `text` breaks a rule, or None when every check passes."""
    if not text:
        return "empty response"
    words = len(text.split())
    if words > MAX_WORDS:
        return f"too long ({words} words, limit {MAX_WORDS})"
    sentences = _sentences(text)
    if len(sentences) > 4:
        return "more than 4 sentences"
    banned = _BANNED_RE.search(text)
    if banned:
        return f"uses banned phrase '{banned.group(1).lower()}'"
    if _SPELLED_NUMBER_RE.search(text):
        return "spells out a number, write digits"
    if facts.sport == "CFB" and _CFB_INJURY_RE.search(text):
        return "mentions injuries, but college football has no reliable injury report"
    p = facts.home_win_prob
    valid = {round(p * 100), round((1 - p) * 100)}
    for match in _PCT_RE.finditer(text):
        if not any(abs(float(match.group(1)) - v) <= 1.0 for v in valid):
            return f"cites a percentage ({match.group(1)}%) the model did not produce"
    sheet = render_fact_sheet(facts)
    # A plain word the sheet uses in lower case is capitalized only to open a sentence.
    unknown = (
        _name_tokens(text) - _name_tokens(sheet) - COMMON_CAPITALIZED
        - set(_LOWER_WORD_RE.findall(sheet))
    )
    if unknown:
        return f"names not in the fact sheet: {', '.join(sorted(unknown))}"
    reason = _numeric_facts_reason(text, sheet)
    if reason:
        return reason
    parsed = [_Sentence.parse(s, facts) for s in sentences]
    market = [s.is_market() for s in parsed]
    if facts.spread_home is None and any(market):
        return "mentions a betting market but no line exists"
    for s in parsed:
        reason = _percentage_reason(s, facts)
        if reason:
            return reason
    for s, is_market in zip(parsed, market, strict=True):
        reason = _claims_reason(s, facts, is_market)
        if not reason and is_market:
            reason = _market_numbers_reason(s, facts)
        reason = reason or _injury_team_reason(s, facts)
        if reason:
            return reason
    return None


# Client errors that a retry cannot fix.
_NON_RETRYABLE = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.BadRequestError,
    anthropic.NotFoundError,
)


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
            # Only the error type: messages can carry URLs or request details.
            kind = type(exc).__name__
            logger.warning("narration attempt %d failed: %s", attempt, kind)
            rejections.append(f"api error: {kind}")
            if isinstance(exc, _NON_RETRYABLE):
                return NarrationResult(text=None, attempts=attempt, rejections=rejections)
            if attempt < MAX_ATTEMPTS:
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
