"""CFB team-name resolver, data-driven from a CFBD-generated alias file.

Resolves CFBD school names ("Ohio State") and Odds-API display names
("Ohio State Buckeyes") to canonical CFB abbrs. The alias file is written
by seed_cfb from CFBD school/mascot/abbreviation/alternate names — never
hand-typed. NFL names stay in team_names.py.
"""

import json
import re
from pathlib import Path

import pandas as pd

ALIASES_PATH = Path(__file__).resolve().parent / "seeds" / "cfb_team_aliases.json"

_cache: dict[str, str] | None = None


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _alt_names(row: dict) -> list[str]:
    alts = row.get("alternateNames")
    if isinstance(alts, list):
        return [a for a in alts if _clean(a)]
    return [a for a in (row.get(f"alt_name{i}") for i in (1, 2, 3)) if _clean(a)]


def derive_abbrs(teams: pd.DataFrame) -> dict[str, str]:
    """school -> unique canonical abbr (CFBD abbreviation, de-collided).

    Row order sets collision priority — callers pass FBS before FCS.
    """
    out: dict[str, str] = {}
    taken: set[str] = set()
    for row in teams.to_dict("records"):
        school = row["school"]
        cand = (_clean(row.get("abbreviation")) or "").upper()
        if not cand:
            cand = normalize(school).replace(" ", "").upper()[:6]
        cand = cand[:16]
        base, n = cand, 2
        while cand in taken:
            cand = f"{base[:14]}{n}"
            n += 1
        taken.add(cand)
        out[school] = cand
    return out


def build_alias_map(teams: pd.DataFrame) -> dict[str, str]:
    """Normalized alias -> abbr; ambiguous aliases are dropped."""
    abbrs = derive_abbrs(teams)
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()

    def add(alias: str | None, abbr: str) -> None:
        key = normalize(alias) if alias else ""
        if not key:
            return
        if key in aliases and aliases[key] != abbr:
            ambiguous.add(key)
            return
        aliases[key] = abbr

    for row in teams.to_dict("records"):
        school = row["school"]
        abbr = abbrs[school]
        add(school, abbr)
        add(abbr, abbr)
        mascot = _clean(row.get("mascot"))
        if mascot:
            add(f"{school} {mascot}", abbr)  # Odds-API display name
        for alt in _alt_names(row):
            add(alt, abbr)

    for key in ambiguous:
        aliases.pop(key, None)
        print(f"cfb_team_names: dropped ambiguous alias {key!r}")
    return aliases


def save_aliases(aliases: dict[str, str]) -> None:
    global _cache
    ALIASES_PATH.write_text(
        json.dumps(aliases, indent=1, sort_keys=True), encoding="utf-8"
    )
    _cache = dict(aliases)


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        if not ALIASES_PATH.exists():
            raise FileNotFoundError(
                "cfb_team_aliases.json missing — run `python -m data_pipeline.seed_cfb` first"
            )
        _cache = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    return _cache


def cfb_to_abbr(name: str, aliases: dict[str, str] | None = None) -> str:
    """Map any external CFB team name to the canonical abbreviation."""
    if not name:
        raise ValueError("empty team name")
    table = aliases if aliases is not None else _load()
    key = normalize(name)
    if key in table:
        return table[key]
    # Prefix fallback on word boundary: "North Dakota State Bison" -> "north dakota state".
    best = ""
    hits: set[str] = set()
    for alias, abbr in table.items():
        if key.startswith(alias + " "):
            if len(alias) > len(best):
                best, hits = alias, {abbr}
            elif len(alias) == len(best):
                hits.add(abbr)
    if len(hits) == 1:
        return next(iter(hits))
    raise KeyError(f"unrecognized CFB team name: {name!r}")
