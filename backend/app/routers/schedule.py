from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import mock_data
from app.cache import cached
from app.config import get_settings
from app.db import get_db
from app.routers import normalize_sport, normalize_status
from app.schemas import ScheduleOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["schedule"])

CACHE_TTL_SECONDS = 60


@router.get(
    "/schedule",
    response_model=ScheduleOut,
    summary="Season schedule grouped by week",
)
def get_schedule(
    season: int = Query(2026, ge=2000, le=2100),
    sport: str = "NFL",
    status: str = Query("all"),
    db: Session = Depends(get_db),
) -> ScheduleOut:
    sport = normalize_sport(sport)
    status = normalize_status(status)
    if get_settings().blitzcast_mock:
        return mock_data.get_schedule(season, sport, status)
    return cached(
        ("schedule", season, sport, status),
        CACHE_TTL_SECONDS,
        lambda: svc.get_schedule(db, season, sport, status),
    )
