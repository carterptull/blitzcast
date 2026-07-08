"""SQLAlchemy ORM models for the Blitzcast schema."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Stadium(Base):
    __tablename__ = "stadiums"

    stadium_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    is_dome: Mapped[bool] = mapped_column(Boolean, default=False)
    surface: Mapped[str] = mapped_column(String(30))


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abbr: Mapped[str] = mapped_column(String(4), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(60))
    conference: Mapped[str] = mapped_column(String(3))
    division: Mapped[str] = mapped_column(String(10))
    stadium_id: Mapped[int | None] = mapped_column(ForeignKey("stadiums.stadium_id"))

    stadium: Mapped[Stadium | None] = relationship()


class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    game_date: Mapped[date] = mapped_column(Date)
    kickoff_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    stadium_id: Mapped[int | None] = mapped_column(ForeignKey("stadiums.stadium_id"))
    is_primetime: Mapped[bool] = mapped_column(Boolean, default=False)
    is_divisional: Mapped[bool] = mapped_column(Boolean, default=False)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    # Closing market numbers from nflverse (historical training feature).
    spread_line: Mapped[float | None] = mapped_column(Float)
    total_line: Mapped[float | None] = mapped_column(Float)
    home_moneyline: Mapped[int | None] = mapped_column(Integer)
    away_moneyline: Mapped[int | None] = mapped_column(Integer)

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    stadium: Mapped[Stadium | None] = relationship()


class TeamGameStat(Base):
    __tablename__ = "team_game_stats"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), primary_key=True)
    points: Mapped[int | None] = mapped_column(Integer)
    yards: Mapped[float | None] = mapped_column(Float)
    epa_offense: Mapped[float | None] = mapped_column(Float)
    epa_defense: Mapped[float | None] = mapped_column(Float)
    turnovers: Mapped[int | None] = mapped_column(Integer)


class TeamRating(Base):
    __tablename__ = "team_ratings"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    elo_rating: Mapped[float] = mapped_column(Float)


class Odds(Base):
    __tablename__ = "odds"
    __table_args__ = (UniqueConstraint("game_id", "source", name="uq_odds_game_source"),)

    odds_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), index=True)
    source: Mapped[str] = mapped_column(String(40))
    spread_home: Mapped[float | None] = mapped_column(Float)
    moneyline_home: Mapped[int | None] = mapped_column(Integer)
    moneyline_away: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Weather(Base):
    __tablename__ = "weather"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), primary_key=True)
    temp_f: Mapped[float | None] = mapped_column(Float)
    wind_mph: Mapped[float | None] = mapped_column(Float)
    precipitation: Mapped[bool | None] = mapped_column(Boolean)
    conditions: Mapped[str | None] = mapped_column(String(80))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Injury(Base):
    __tablename__ = "injuries"
    __table_args__ = (
        UniqueConstraint("game_id", "team_id", "player_name", name="uq_injury_game_player"),
    )

    injury_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    player_name: Mapped[str] = mapped_column(String(80))
    position: Mapped[str | None] = mapped_column(String(6))
    status: Mapped[str | None] = mapped_column(String(30))
    report_date: Mapped[date | None] = mapped_column(Date)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("game_id", "model_version", name="uq_prediction_game_version"),
    )

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), index=True)
    model_version: Mapped[str] = mapped_column(String(20))
    home_win_prob: Mapped[float] = mapped_column(Float)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shap_top_features: Mapped[list | None] = mapped_column(JsonType)
    llm_narrative: Mapped[str | None] = mapped_column(Text)
