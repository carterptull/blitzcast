"""Pydantic response models -- the API contract the frontend builds against."""

from datetime import datetime

from pydantic import BaseModel


class TeamOut(BaseModel):
    id: int
    abbr: str
    name: str
    conference: str
    division: str
    logo_url: str


class GameTeam(BaseModel):
    abbr: str
    name: str


class GameSummary(BaseModel):
    game_id: str
    kickoff: datetime | None
    home: GameTeam
    away: GameTeam
    is_primetime: bool
    status: str
    has_prediction: bool
    home_win_prob: float | None = None


class WeekOut(BaseModel):
    week: int
    games: list[GameSummary]


class ScheduleOut(BaseModel):
    season: int
    weeks: list[WeekOut]


class VenueOut(BaseModel):
    name: str | None
    city: str | None
    is_dome: bool | None


class TeamDetail(BaseModel):
    abbr: str
    name: str
    record: str
    logo_url: str
    win_prob: float | None


class OddsOut(BaseModel):
    spread_home: float | None
    moneyline_home: int | None
    moneyline_away: int | None
    total: float | None


class WeatherOut(BaseModel):
    temp_f: float | None
    wind_mph: float | None
    precipitation: bool | None
    conditions: str | None


class FactorOut(BaseModel):
    label: str
    value: float
    direction: str


class PredictionOut(BaseModel):
    game_id: str
    season: int
    week: int
    kickoff: datetime | None
    venue: VenueOut
    is_primetime: bool
    is_divisional: bool
    home: TeamDetail
    away: TeamDetail
    odds: OddsOut | None
    weather: WeatherOut | None
    factors: list[FactorOut]
    narrative: str | None
    model_version: str | None
    predicted_at: datetime | None
    prediction_status: str
