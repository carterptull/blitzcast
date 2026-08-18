from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.routers import normalize_sport, normalize_status
from app.schemas import GameSummary
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["games"])


@router.get(
    "/games",
    response_model=list[GameSummary],
    summary="Games for one week of a season",
)
def get_games(
    week: int,
    season: int = 2026,
    sport: str = "NFL",
    status: str = Query("all"),
    db: Session = Depends(get_db),
) -> list[GameSummary]:
    sport = normalize_sport(sport)
    status = normalize_status(status)
    if get_settings().blitzcast_mock:
        return mock_data.get_games(season, week, sport, status)
    return svc.get_games(db, season, week, sport, status)
