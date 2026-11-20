from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import mock_data
from app.config import get_settings
from app.db import get_db
from app.postseason import round_for_slug
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
    week: int = Query(..., ge=0, le=30),
    season: int = Query(2026, ge=2000, le=2100),
    sport: str = "NFL",
    status: str = Query("all"),
    round: str | None = Query(None, pattern=r"^[a-z-]{1,24}$"),
    db: Session = Depends(get_db),
) -> list[GameSummary]:
    sport = normalize_sport(sport)
    status = normalize_status(status)
    if round is not None and round_for_slug(round) is None:
        raise HTTPException(status_code=422, detail="unknown round")
    if get_settings().blitzcast_mock:
        return mock_data.get_games(season, week, sport, status, round)
    return svc.get_games(db, season, week, sport, status, round)
