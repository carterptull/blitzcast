from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.routers import normalize_sport
from app.schemas import RecordOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["record"])


@router.get("/record", response_model=RecordOut, summary="Prediction record")
def get_record(
    sport: str | None = None, season: int = 2026, db: Session = Depends(get_db)
) -> RecordOut:
    normalized_sport = normalize_sport(sport) if sport else None
    if get_settings().blitzcast_mock:
        return mock_data.get_record(season, normalized_sport)
    return svc.get_record(db, season=season, sport=normalized_sport)
