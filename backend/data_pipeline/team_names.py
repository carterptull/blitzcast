"""Canonical team abbreviation mapping.

Every external team identifier (nflverse abbr variants, Odds API full names,
ESPN names) must be routed through `to_abbr` before touching the database.
"""

CANONICAL_ABBRS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
}

# Alternate abbreviations seen across sources (nflverse, ESPN, pro-football-ref).
_ABBR_ALIASES = {
    "LAR": "LA",
    "WSH": "WAS",
    "JAC": "JAX",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
}

# Full names (The Odds API, ESPN displayName) -> canonical abbr.
_FULL_NAMES = {
    "arizona cardinals": "ARI",
    "atlanta falcons": "ATL",
    "baltimore ravens": "BAL",
    "buffalo bills": "BUF",
    "carolina panthers": "CAR",
    "chicago bears": "CHI",
    "cincinnati bengals": "CIN",
    "cleveland browns": "CLE",
    "dallas cowboys": "DAL",
    "denver broncos": "DEN",
    "detroit lions": "DET",
    "green bay packers": "GB",
    "houston texans": "HOU",
    "indianapolis colts": "IND",
    "jacksonville jaguars": "JAX",
    "kansas city chiefs": "KC",
    "los angeles rams": "LA",
    "los angeles chargers": "LAC",
    "las vegas raiders": "LV",
    "miami dolphins": "MIA",
    "minnesota vikings": "MIN",
    "new england patriots": "NE",
    "new orleans saints": "NO",
    "new york giants": "NYG",
    "new york jets": "NYJ",
    "philadelphia eagles": "PHI",
    "pittsburgh steelers": "PIT",
    "seattle seahawks": "SEA",
    "san francisco 49ers": "SF",
    "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN",
    "washington commanders": "WAS",
    "washington football team": "WAS",
    "washington redskins": "WAS",
    "oakland raiders": "LV",
    "san diego chargers": "LAC",
    "st. louis rams": "LA",
    "st louis rams": "LA",
}

# ESPN CDN logo slugs where they differ from the canonical abbr.
_LOGO_SLUGS = {"LA": "lar", "WAS": "wsh"}


def to_abbr(name: str) -> str:
    """Map any external team identifier to the canonical abbreviation."""
    if not name:
        raise ValueError("empty team name")
    cleaned = name.strip()
    upper = cleaned.upper()
    if upper in CANONICAL_ABBRS:
        return upper
    if upper in _ABBR_ALIASES:
        return _ABBR_ALIASES[upper]
    lower = cleaned.lower()
    if lower in _FULL_NAMES:
        return _FULL_NAMES[lower]
    raise KeyError(f"unrecognized team name: {name!r}")


def logo_url(abbr: str) -> str:
    slug = _LOGO_SLUGS.get(abbr, abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png"


def nickname(full_name: str) -> str:
    return full_name.rsplit(" ", 1)[-1]
