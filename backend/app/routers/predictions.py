from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.schemas import PredictionOut
from app.services import predictions as svc

router = APIRouter(prefix="/api", tags=["predictions"])


@router.get(
    "/predictions/{game_id}",
    response_model=PredictionOut,
    summary="Full matchup prediction detail",
    description=(
        "Returns the full matchup detail. If the game exists but no prediction "
        "has been generated yet, prediction_status is 'pending' and factors is "
        "empty. Unknown game_id returns 404."
    ),
)
def get_prediction(game_id: str, db: Session = Depends(get_db)) -> PredictionOut:
    if get_settings().blitzcast_mock:
        detail = mock_data.get_prediction_detail(game_id)
    else:
        detail = svc.get_prediction_detail(db, game_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="game not found")
    return detail
