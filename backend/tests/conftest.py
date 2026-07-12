import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import (  # noqa: E402
    SPORT_CFB,
    Base,
    Game,
    Injury,
    PollRank,
    Prediction,
    Stadium,
    Team,
    TeamGameStat,
)

TEAMS = [
    ("KC", "Kansas City Chiefs", "AFC", "West"),
    ("BUF", "Buffalo Bills", "AFC", "East"),
    ("PHI", "Philadelphia Eagles", "NFC", "East"),
    ("DAL", "Dallas Cowboys", "NFC", "East"),
]

# (abbr, name, conference, tier, espn_id, color)
CFB_TEAMS = [
    ("UGA", "Georgia", "SEC", "FBS", 61, "#BA0C2F"),
    ("ALA", "Alabama", "SEC", "FBS", 333, "#9E1B32"),
    ("MER", "Mercer", "SoCon", "FCS", None, None),
]


def _seed_cfb(db: Session, stadium: Stadium) -> None:
    teams: dict[str, Team] = {}
    for abbr, name, conf, tier, espn_id, color in CFB_TEAMS:
        team = Team(
            sport=SPORT_CFB, abbr=abbr, name=name, conference=conf,
            division=None, tier=tier, espn_id=espn_id, color=color,
            stadium_id=stadium.stadium_id,
        )
        db.add(team)
        teams[abbr] = team
    db.flush()

    # AP + Coaches polls entering 2026 week 1; AP must be preferred.
    for poll, uga_rank, ala_rank in (("AP Top 25", 3, 7), ("Coaches Poll", 4, 8)):
        for abbr, rank in (("UGA", uga_rank), ("ALA", ala_rank)):
            db.add(
                PollRank(
                    sport=SPORT_CFB, season=2026, week=1, poll=poll,
                    team_id=teams[abbr].team_id, rank=rank,
                )
            )

    kickoff = datetime(2026, 9, 5, 19, 30, tzinfo=UTC)
    db.add(
        Game(
            game_id="cfb_401800001",
            sport=SPORT_CFB, season=2026, week=1,
            game_date=kickoff.date(), kickoff_time=kickoff,
            home_team_id=teams["ALA"].team_id,
            away_team_id=teams["UGA"].team_id,
            stadium_id=stadium.stadium_id,
            is_primetime=True, is_divisional=True,
            status="scheduled",
        )
    )
    # Week 2 FBS-vs-FCS game with a TBD (NULL) kickoff.
    db.add(
        Game(
            game_id="cfb_401800002",
            sport=SPORT_CFB, season=2026, week=2,
            game_date=date(2026, 9, 12), kickoff_time=None,
            home_team_id=teams["UGA"].team_id,
            away_team_id=teams["MER"].team_id,
            stadium_id=stadium.stadium_id,
            is_primetime=False, is_divisional=False,
            status="scheduled",
        )
    )
    db.add(
        Prediction(
            game_id="cfb_401800001",
            model_version="cfb-0.1.0",
            home_win_prob=0.55,
            predicted_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            shap_top_features=[
                {"feature": "poll_strength_diff", "label": "AP poll standing edge",
                 "value": 0.08, "direction": "home"},
            ],
            llm_narrative=None,
        )
    )


def _seed(db: Session) -> None:
    stadium = Stadium(
        name="Test Field", city="Testville", lat=39.0, lon=-94.0,
        is_dome=False, surface="grass",
    )
    db.add(stadium)
    db.flush()

    teams: dict[str, Team] = {}
    for abbr, name, conf, division in TEAMS:
        team = Team(
            abbr=abbr, name=name, conference=conf, division=division,
            stadium_id=stadium.stadium_id,
        )
        db.add(team)
        teams[abbr] = team
    db.flush()

    # 2025: six played weeks. KC always wins at home; the PHI/DAL game
    # flips to an away win on even weeks so both classes exist.
    base_kickoff = datetime(2025, 9, 7, 17, 0, tzinfo=UTC)
    for week in range(1, 7):
        kickoff = base_kickoff + timedelta(days=7 * (week - 1))
        for home, away in (("KC", "BUF"), ("PHI", "DAL")):
            game_id = f"2025_{week:02d}_{away}_{home}"
            away_wins = home == "PHI" and week % 2 == 0
            db.add(
                Game(
                    game_id=game_id,
                    season=2025, week=week,
                    game_date=kickoff.date(),
                    kickoff_time=kickoff,
                    home_team_id=teams[home].team_id,
                    away_team_id=teams[away].team_id,
                    stadium_id=stadium.stadium_id,
                    is_primetime=False, is_divisional=(home == "PHI"),
                    home_score=17 if away_wins else 24,
                    away_score=24 if away_wins else 17,
                    status="final",
                    spread_line=3.0, total_line=45.0,
                    home_moneyline=-150, away_moneyline=130,
                )
            )
            for team_abbr, epa_off, epa_def, tos in (
                (home, -0.05 if away_wins else 0.10, 0.08 if away_wins else -0.05, 1),
                (away, 0.10 if away_wins else -0.05, -0.05 if away_wins else 0.08, 2),
            ):
                is_winner = (team_abbr == away) if away_wins else (team_abbr == home)
                db.add(
                    TeamGameStat(
                        game_id=game_id,
                        team_id=teams[team_abbr].team_id,
                        points=24 if is_winner else 17,
                        yards=350.0, epa_offense=epa_off,
                        epa_defense=epa_def, turnovers=tos,
                    )
                )

    # 2026 week 1: scheduled, market lines present.
    kickoff_26 = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    for home, away, spread in (("KC", "BUF", 2.5), ("DAL", "PHI", -3.5)):
        db.add(
            Game(
                game_id=f"2026_01_{away}_{home}",
                season=2026, week=1,
                game_date=kickoff_26.date(),
                kickoff_time=kickoff_26,
                home_team_id=teams[home].team_id,
                away_team_id=teams[away].team_id,
                stadium_id=stadium.stadium_id,
                is_primetime=True, is_divisional=(home == "DAL"),
                status="scheduled",
                spread_line=spread, total_line=47.0,
                home_moneyline=-130 if spread > 0 else 150,
                away_moneyline=110 if spread > 0 else -170,
            )
        )

    db.add(
        Injury(
            game_id="2026_01_BUF_KC",
            team_id=teams["BUF"].team_id,
            player_name="Test Quarterback", position="QB",
            status="Out", report_date=date(2026, 9, 11),
        )
    )
    db.add(
        Prediction(
            game_id="2026_01_BUF_KC",
            model_version="0.1.0",
            home_win_prob=0.61,
            predicted_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
            shap_top_features=[
                {"feature": "elo_diff", "label": "Team rating (Elo) edge",
                 "value": 0.12, "direction": "home"},
            ],
            llm_narrative=None,
        )
    )
    _seed_cfb(db, stadium)
    db.commit()


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    _seed(session)
    yield session
    session.close()


@pytest.fixture()
def client(engine, db):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
