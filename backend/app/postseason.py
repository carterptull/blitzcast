"""Postseason rounds, labels and event names.

Spec: docs/superpowers/specs/2026-11-19-postseason-design.md
"""

import re
from typing import Literal, get_args

SEASON_REGULAR = "regular"
SEASON_POSTSEASON = "postseason"
CFB_POSTSEASON_WEEK = 17
NFL_GAME_TYPES = ("REG", "WC", "DIV", "CON", "SB")

Round = Literal[
    "conf_championship", "wild_card", "divisional", "conference", "super_bowl", "bowl",
    "cfp_first_round", "cfp_quarterfinal", "cfp_semifinal", "cfp_championship", "cfp_other",
]
ROUNDS: tuple[Round, ...] = get_args(Round)

ROUND_SLUGS: dict[Round, str] = {
    "wild_card": "wild-card",
    "divisional": "divisional",
    "conference": "conference",
    "super_bowl": "super-bowl",
    "bowl": "bowls",
    "cfp_first_round": "cfp-first-round",
    "cfp_quarterfinal": "cfp-quarterfinals",
    "cfp_semifinal": "cfp-semifinals",
    "cfp_championship": "cfp-title",
    "cfp_other": "cfp-other",
}
_ROUND_BY_SLUG = {slug: r for r, slug in ROUND_SLUGS.items()}

# (eyebrow label, chip group line, chip short label)
ROUND_LABELS: dict[Round, tuple[str, str, str | None]] = {
    "conf_championship": ("Conference Championships", "Champ", None),
    "wild_card": ("Wild Card", "Round", "WC"),
    "divisional": ("Divisional", "Round", "DIV"),
    "conference": ("Conference Championships", "Round", "CONF"),
    "super_bowl": ("Super Bowl", "Round", "SB"),
    "bowl": ("Bowl Season", "Non-CFP", "Bowls"),
    "cfp_first_round": ("CFP First Round", "CFP", "R1"),
    "cfp_quarterfinal": ("CFP Quarterfinals", "CFP", "QF"),
    "cfp_semifinal": ("CFP Semifinals", "CFP", "SF"),
    "cfp_championship": ("National Championship", "CFP", "Title"),
    "cfp_other": ("College Football Playoff", "CFP", "CFP"),
}

_GENERIC_NAMES: dict[Round, str] = {
    "conf_championship": "Conference Championship",
    "wild_card": "Wild Card",
    "divisional": "Divisional Round",
    "conference": "Conference Championship",
    "super_bowl": "Super Bowl",
    "bowl": "Bowl game",
    "cfp_first_round": "CFP First Round",
    "cfp_quarterfinal": "CFP Quarterfinal",
    "cfp_semifinal": "CFP Semifinal",
    "cfp_championship": "CFP National Championship",
    "cfp_other": "College Football Playoff",
}

# Plain words for a CFP round in a sentence ("College Football Playoff quarterfinal").
CFP_ROUND_WORDS: dict[Round, str] = {
    "cfp_first_round": "first round",
    "cfp_quarterfinal": "quarterfinal",
    "cfp_semifinal": "semifinal",
    "cfp_championship": "national championship",
}

_NFL_ROUNDS: dict[str, Round] = {
    "WC": "wild_card", "DIV": "divisional", "CON": "conference", "SB": "super_bowl",
}
_NFL_EVENT_SUFFIX: dict[Round, str] = {
    "wild_card": "Wild Card", "divisional": "Divisional", "conference": "Championship",
}
_CFP_ROUNDS: dict[str, Round] = {
    "first_round": "cfp_first_round",
    "quarterfinal": "cfp_quarterfinal",
    "semifinal": "cfp_semifinal",
    "championship": "cfp_championship",
}

_LONG_DASH_RE = re.compile(r"\s*[–—]\s*")
_SPONSOR_TAIL_RE = re.compile(r"\s+(?:presented|powered|hosted)\s+by\b.*$", re.IGNORECASE)
_EVENT_NAME_RE = re.compile(r"^[A-Za-z0-9'&.,\- ]{3,48}$")
_EVENT_AD_RE = re.compile(r"\b(?:pick|odds|site|bets?|wager)\b", re.IGNORECASE)
_EVENT_JOINERS = {
    "of", "at", "the", "and", "to", "for", "by", "in", "on", "de", "la", "del", "du", "a",
}
EVENT_NAME_MAX = 64  # Game.event_name is String(64)


def round_for_slug(slug: str) -> Round | None:
    return _ROUND_BY_SLUG.get(slug)


def nfl_round(game_type: str) -> tuple[str, Round | None]:
    if game_type == "REG":
        return SEASON_REGULAR, None
    if game_type in _NFL_ROUNDS:
        return SEASON_POSTSEASON, _NFL_ROUNDS[game_type]
    raise ValueError(f"unknown NFL game_type {game_type!r}")


def roman(n: int) -> str:
    out = []
    for value, numeral in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        count, n = divmod(n, value)
        out.append(numeral * count)
    return "".join(out)


def super_bowl_name(season: int) -> str:
    return f"Super Bowl {roman(season - 1965)}"


def nfl_event_name(round_: Round, home_conference: str | None, season: int) -> str:
    if round_ == "super_bowl":
        return super_bowl_name(season)
    suffix = _NFL_EVENT_SUFFIX[round_]
    return f"{home_conference} {suffix}" if home_conference else suffix


def cfb_playoff_round(raw: str | None) -> Round:
    return _CFP_ROUNDS.get(raw or "", "cfp_other")


def generic_event_name(round_: Round) -> str:
    return _GENERIC_NAMES[round_]


def clean_event_name(raw: str | None) -> str | None:
    """Feed text as a safe event name, or None when it does not read like one."""
    # Imported here: fact_sheet imports the predictions service, which imports this module.
    from app.services.fact_sheet import _AD_WORD_RE, _LINK_WORD_RE, _clean

    if raw is None:
        return None
    parts = [_clean(part, 64) for part in _LONG_DASH_RE.split(raw)]
    text = ", ".join(p for p in parts if p)
    text = " ".join(_SPONSOR_TAIL_RE.sub("", text).split())
    if not _EVENT_NAME_RE.match(text) or sum(ch.isdigit() for ch in text) > 2:
        return None
    if _LINK_WORD_RE.search(text) or _AD_WORD_RE.search(text) or _EVENT_AD_RE.search(text):
        return None
    # Names are Title Case: a lowercase word other than a small joiner is prose.
    for word in re.findall(r"[A-Za-z][\w']*", text):
        if word[0].islower() and word not in _EVENT_JOINERS:
            return None
    return text


def cfp_event_name(raw_round: str | None, bowl_name: str | None) -> str:
    round_ = cfb_playoff_round(raw_round)
    generic = generic_event_name(round_)
    bowl = clean_event_name(bowl_name)
    if bowl and bowl.endswith("Bowl") and len(f"{bowl}, {generic}") <= EVENT_NAME_MAX:
        return f"{bowl}, {generic}"
    return generic


def is_conf_championship(
    notes: str | None, home_conference: str | None, away_conference: str | None
) -> bool:
    return bool(
        notes
        and "championship" in notes.lower()
        and home_conference
        and home_conference == away_conference
    )
