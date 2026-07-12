from fastapi import HTTPException

from app.models import SPORT_CFB, SPORT_NFL


def normalize_sport(sport: str) -> str:
    """Case-insensitive sport query param -> canonical constant; 422 if unknown."""
    normalized = sport.upper()
    if normalized not in (SPORT_NFL, SPORT_CFB):
        raise HTTPException(status_code=422, detail=f"unknown sport '{sport}'")
    return normalized
