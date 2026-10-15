"""Calendar-derived default season for the batch jobs."""

from datetime import date


def current_season(sport: str, today: date | None = None) -> int:
    """NFL rolls over in March, after the Super Bowl; CFB in June. Earlier
    months belong to the previous season."""
    today = today or date.today()
    first_month = 3 if sport.lower() == "nfl" else 6
    return today.year if today.month >= first_month else today.year - 1


def resolve_season(season: int | None, sport: str) -> int:
    return season if season is not None else current_season(sport)
