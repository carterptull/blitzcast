"""compute_ratings sport scoping: a CFB recompute never wipes NFL rows."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import SPORT_CFB, SPORT_NFL, Base, Game, Team, TeamRating
from ml.compute_ratings import compute_ratings


def _seed(db: Session) -> dict[str, Team]:
    teams = {}
    for abbr, name, conf, tier, sport in (
        ("KC", "Kansas City Chiefs", "AFC", None, SPORT_NFL),
        ("BUF", "Buffalo Bills", "AFC", None, SPORT_NFL),
        ("UGA", "Georgia", "SEC", "FBS", SPORT_CFB),
        ("MERC", "Mercer", "SoCon", "FCS", SPORT_CFB),
    ):
        team = Team(sport=sport, abbr=abbr, name=name, conference=conf, tier=tier)
        db.add(team)
        teams[abbr] = team
    db.flush()

    k = datetime(2025, 9, 6, 19, 0, tzinfo=UTC)
    for game_id, sport, home, away, hs, as_ in (
        ("2025_01_BUF_KC", SPORT_NFL, "KC", "BUF", 24, 17),
        ("2025_02_BUF_KC", SPORT_NFL, "KC", "BUF", 31, 20),
        ("cfb_10", SPORT_CFB, "UGA", "MERC", 42, 7),
    ):
        db.add(
            Game(
                game_id=game_id, sport=sport, season=2025,
                week=int(game_id.split("_")[1]) if sport == SPORT_NFL else 1,
                game_date=k.date(), kickoff_time=k,
                home_team_id=teams[home].team_id, away_team_id=teams[away].team_id,
                is_primetime=False, is_divisional=False,
                home_score=hs, away_score=as_, status="final",
            )
        )
        k += timedelta(days=7)
    db.commit()
    return teams


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    _seed(db)
    yield db
    db.close()
    engine.dispose()


def _ratings(db: Session, sport: str) -> dict:
    return {
        (r.team_id, r.season, r.week): r.elo_rating
        for r in db.scalars(select(TeamRating).where(TeamRating.sport == sport))
    }


def test_cfb_recompute_leaves_nfl_rows_intact(session):
    compute_ratings(session, SPORT_NFL)
    session.commit()
    nfl_before = _ratings(session, SPORT_NFL)
    assert nfl_before

    compute_ratings(session, SPORT_CFB)
    session.commit()
    assert _ratings(session, SPORT_NFL) == nfl_before

    cfb = _ratings(session, SPORT_CFB)
    assert cfb
    # Re-running CFB is idempotent and still leaves NFL untouched.
    compute_ratings(session, SPORT_CFB)
    session.commit()
    assert _ratings(session, SPORT_CFB) == cfb
    assert _ratings(session, SPORT_NFL) == nfl_before


def test_cfb_snapshots_use_fcs_floor(session):
    teams = {t.abbr: t for t in session.scalars(select(Team))}
    compute_ratings(session, SPORT_CFB)
    session.commit()
    cfb = _ratings(session, SPORT_CFB)
    assert cfb[(teams["UGA"].team_id, 2025, 1)] == 1500.0
    assert cfb[(teams["MERC"].team_id, 2025, 1)] == 1150.0


def test_nfl_recompute_leaves_cfb_rows_intact(session):
    compute_ratings(session, SPORT_CFB)
    session.commit()
    cfb_before = _ratings(session, SPORT_CFB)
    assert cfb_before

    compute_ratings(session, SPORT_NFL)
    session.commit()
    assert _ratings(session, SPORT_CFB) == cfb_before
