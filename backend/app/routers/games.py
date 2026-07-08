from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.schemas import GameSummary
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["games"])


@router.get(
    "/games",
    response_model=list[GameSummary],
    summary="Games for one week of a season",
)
def get_games(
    week: int, season: int = 2026, db: Session = Depends(get_db)
) -> list[GameSummary]:
    if get_settings().blitzcast_mock:
        return mock_data.get_games(season, week)
    return svc.get_games(db, season, week)
