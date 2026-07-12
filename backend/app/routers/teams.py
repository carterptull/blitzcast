from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.routers import normalize_sport
from app.schemas import TeamOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["teams"])


@router.get("/teams", response_model=list[TeamOut], summary="List a sport's teams")
def get_teams(sport: str = "NFL", db: Session = Depends(get_db)) -> list[TeamOut]:
    sport = normalize_sport(sport)
    if get_settings().blitzcast_mock:
        return mock_data.list_teams(sport)
    return svc.list_teams(db, sport)
