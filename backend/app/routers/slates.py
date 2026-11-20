from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import mock_data
from app.cache import cached
from app.config import get_settings
from app.db import get_db
from app.routers import normalize_sport
from app.schemas import SlateOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["slates"])

CACHE_TTL_SECONDS = 60


@router.get(
    "/slates",
    response_model=list[SlateOut],
    summary="Regular-season weeks and postseason rounds for a season",
)
def get_slates(
    season: int = Query(2026, ge=2000, le=2100),
    sport: str = "NFL",
    db: Session = Depends(get_db),
) -> list[SlateOut]:
    sport = normalize_sport(sport)
    if get_settings().blitzcast_mock:
        return mock_data.get_slates(season, sport)
    return cached(
        ("slates", season, sport),
        CACHE_TTL_SECONDS,
        lambda: svc.get_slates(db, season, sport),
    )
