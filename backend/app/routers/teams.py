from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.schemas import TeamOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["teams"])


@router.get("/teams", response_model=list[TeamOut], summary="List all 32 teams")
def get_teams(db: Session = Depends(get_db)) -> list[TeamOut]:
    if get_settings().blitzcast_mock:
        return mock_data.list_teams()
    return svc.list_teams(db)
