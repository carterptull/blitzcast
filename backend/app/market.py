"""Sanity rules for quoted betting prices, shared by ingest, features, and the API."""

# Books and CFBD quote this as "no real price" on the extreme side of a blowout.
NO_QUOTE_SENTINEL = 100_000


def real_moneyline(value):
    return None if value is None or abs(value) >= NO_QUOTE_SENTINEL else value


def _implied(ml: float) -> float:
    return -ml / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def plausible_moneylines(home, away) -> bool:
    """Both sides real, and implied probabilities sum to a normal book (vig
    included). Rejects sentinel pairs and both-favorite glitches."""
    if real_moneyline(home) is None or real_moneyline(away) is None:
        return False
    return 0.95 <= _implied(home) + _implied(away) <= 1.25
