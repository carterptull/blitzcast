"""CFB feature building: tier/poll features, poll leakage, sport isolation.

Self-contained fixtures (does not use the shared conftest seed).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import SPORT_CFB, SPORT_NFL, Base, Game, PollRank, Team, TeamGameStat
from ml.features import FEATURE_COLUMNS, build_features


def _add_game(db, game_id, sport, season, week, kickoff, home, away, home_score, away_score):
    db.add(
        Game(
            game_id=game_id, sport=sport, season=season, week=week,
            game_date=kickoff.date(), kickoff_time=kickoff,
            home_team_id=home.team_id, away_team_id=away.team_id,
            is_primetime=False, is_divisional=False,
            home_score=home_score, away_score=away_score,
            status="final" if home_score is not None else "scheduled",
        )
    )
    if home_score is not None:
        for team, pts in ((home, home_score), (away, away_score)):
            db.add(
                TeamGameStat(
                    game_id=game_id, team_id=team.team_id, points=pts,
                    yards=300.0, epa_offense=0.05, epa_defense=-0.02, turnovers=1,
                )
            )


def _seed(db: Session) -> dict[str, Team]:
    teams = {}
    for abbr, name, conf, tier, sport in (
        ("UGA", "Georgia", "SEC", "FBS", SPORT_CFB),
        ("BAMA", "Alabama", "SEC", "FBS", SPORT_CFB),
        ("MERC", "Mercer", "SoCon", "FCS", SPORT_CFB),
        ("KC", "Kansas City Chiefs", "AFC", None, SPORT_NFL),
        ("BUF", "Buffalo Bills", "AFC", None, SPORT_NFL),
    ):
        team = Team(sport=sport, abbr=abbr, name=name, conference=conf, tier=tier)
        db.add(team)
        teams[abbr] = team
    db.flush()

    k = datetime(2025, 8, 30, 19, 0, tzinfo=UTC)
    wk = timedelta(days=7)
    _add_game(db, "cfb_1", SPORT_CFB, 2025, 1, k, teams["UGA"], teams["MERC"], 42, 7)
    _add_game(db, "cfb_2", SPORT_CFB, 2025, 2, k + wk, teams["UGA"], teams["BAMA"], 24, 21)
    _add_game(db, "cfb_3", SPORT_CFB, 2025, 3, k + 2 * wk, teams["BAMA"], teams["UGA"], 31, 10)
    _add_game(db, "2025_01_BUF_KC", SPORT_NFL, 2025, 1, k + wk, teams["KC"], teams["BUF"], 24, 17)

    # Polls stored as the ranking ENTERING (season, week).
    for season, week, poll, abbr, rank in (
        (2025, 2, "AP Top 25", "UGA", 5),
        (2025, 2, "Coaches Poll", "UGA", 10),
        # Published after week 2's games: must never leak into week 2 features.
        (2025, 3, "AP Top 25", "BAMA", 1),
        (2025, 3, "AP Top 25", "UGA", 2),
    ):
        db.add(
            PollRank(
                sport=SPORT_CFB, season=season, week=week, poll=poll,
                team_id=teams[abbr].team_id, rank=rank,
            )
        )
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


def _row(df, game_id):
    rows = df[df["game_id"] == game_id]
    assert len(rows) == 1
    return rows.iloc[0]


def test_feature_columns_include_cfb_signals():
    assert "tier_diff" in FEATURE_COLUMNS
    assert "poll_strength_diff" in FEATURE_COLUMNS


def test_cfb_tier_diff(session):
    df = build_features(session, sport=SPORT_CFB)
    assert _row(df, "cfb_1")["tier_diff"] == 1.0  # FBS home vs FCS away
    assert _row(df, "cfb_2")["tier_diff"] == 0.0  # FBS vs FBS


def test_poll_uses_only_ranking_entering_the_week(session):
    df = build_features(session, sport=SPORT_CFB)
    # Week 1: no poll stored -> 0.
    assert _row(df, "cfb_1")["poll_strength_diff"] == 0.0
    # Week 2: UGA is AP #5 entering the week (26-5=21), BAMA unranked.
    # BAMA's #1 rank entering week 3 must NOT leak back (it would give -4).
    assert _row(df, "cfb_2")["poll_strength_diff"] == 21.0
    # Week 3: home BAMA #1 (25) vs away UGA #2 (24).
    assert _row(df, "cfb_3")["poll_strength_diff"] == 1.0


def test_ap_poll_preferred_over_coaches(session):
    # UGA is AP #5 and Coaches #10 entering week 2; AP wins -> 21, not 16.
    df = build_features(session, sport=SPORT_CFB)
    assert _row(df, "cfb_2")["poll_strength_diff"] == 21.0


def test_nfl_build_yields_zero_cfb_signals(session):
    df = build_features(session)
    assert (df["tier_diff"] == 0.0).all()
    assert (df["poll_strength_diff"] == 0.0).all()


def test_sport_isolation(session):
    nfl = build_features(session)
    cfb = build_features(session, sport=SPORT_CFB)
    assert set(nfl["game_id"]) == {"2025_01_BUF_KC"}
    assert set(cfb["game_id"]) == {"cfb_1", "cfb_2", "cfb_3"}


def test_cfb_season_with_no_played_games_builds_features():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        teams = {}
        for abbr, name, tier in (("UGA", "Georgia", "FBS"), ("BAMA", "Alabama", "FBS")):
            teams[abbr] = Team(sport=SPORT_CFB, abbr=abbr, name=name, conference="SEC", tier=tier)
            db.add(teams[abbr])
        db.flush()
        k = datetime(2026, 8, 29, 19, 0, tzinfo=UTC)
        _add_game(db, "cfb_a", SPORT_CFB, 2026, 1, k, teams["UGA"], teams["BAMA"], None, None)
        _add_game(
            db, "cfb_b", SPORT_CFB, 2026, 2, k + timedelta(days=7),
            teams["BAMA"], teams["UGA"], None, None,
        )
        db.commit()
        df = build_features(db, sport=SPORT_CFB)
        assert set(df["game_id"]) == {"cfb_a", "cfb_b"}
        assert set(FEATURE_COLUMNS) <= set(df.columns)
        assert df["epa_off_diff"].isna().all() and df["win_pct_diff"].isna().all()
        assert df["home_win"].isna().all()
    finally:
        db.close()
        engine.dispose()


def test_tier_carried_in_metadata(session):
    cfb = build_features(session, sport=SPORT_CFB)
    row = _row(cfb, "cfb_1")
    assert row["home_tier"] == "FBS"
    assert row["away_tier"] == "FCS"


def _add_bowl_and_leaky_poll(session):
    teams = {t.abbr: t for t in session.query(Team)}
    k = datetime(2025, 12, 31, 20, 0, tzinfo=UTC)
    _add_game(session, "cfb_bowl", SPORT_CFB, 2025, 17, k, teams["UGA"], teams["BAMA"], None, None)
    session.query(Game).filter(Game.game_id == "cfb_bowl").one().season_type = "postseason"
    # A poll filed at a postseason slate week (e.g. the final poll) must never be read.
    session.add(PollRank(sport=SPORT_CFB, season=2025, week=17, poll="AP Top 25",
                         team_id=teams["UGA"].team_id, rank=25))
    _add_game(session, "2025_22_BUF_KC", SPORT_NFL, 2025, 22, k + timedelta(days=40),
              teams["KC"], teams["BUF"], None, None)
    session.commit()
    return teams


def test_postseason_feature_poll_strength_from_latest_regular_poll(session):
    """PS-M1: a bowl's poll feature uses the latest regular-season poll (week 3 here)."""
    _add_bowl_and_leaky_poll(session)
    df = build_features(session, sport=SPORT_CFB)
    # Latest regular poll: UGA #2 (24) home vs BAMA #1 (25) away.
    assert _row(df, "cfb_bowl")["poll_strength_diff"] == -1.0
    assert _row(df, "cfb_3")["poll_strength_diff"] == 1.0


def test_postseason_feature_never_reads_a_postseason_poll(session):
    """PS-M2: a poll stored at a postseason week never reaches a bowl's features."""
    _add_bowl_and_leaky_poll(session)
    df = build_features(session, sport=SPORT_CFB)
    # Joining the week-17 row (UGA #25 -> 1.0, BAMA unranked) would give +1.0.
    assert _row(df, "cfb_bowl")["poll_strength_diff"] == -1.0


def test_postseason_week_number_feature_clamped_to_16(session):
    """PS-M3: CFB postseason week_number is clamped to 16; NFL playoff weeks are unchanged."""
    _add_bowl_and_leaky_poll(session)
    assert _row(build_features(session, sport=SPORT_CFB), "cfb_bowl")["week_number"] == 16.0
    assert _row(build_features(session), "2025_22_BUF_KC")["week_number"] == 22.0
    assert _row(build_features(session, sport=SPORT_CFB), "cfb_3")["week_number"] == 3.0


def test_postseason_ranks_use_latest_regular_poll(session):
    """PS-M1: displayed and narrated ranks for week 17 come from the latest regular poll."""
    from app.jobs.predict_week import ranks_for_week
    from app.services.predictions import _poll_ranks_by_week, poll_ranks_entering

    teams = _add_bowl_and_leaky_poll(session)
    latest = {teams["BAMA"].team_id: 1, teams["UGA"].team_id: 2}
    assert poll_ranks_entering(session, SPORT_CFB, 2025, 17) == latest
    assert _poll_ranks_by_week(session, SPORT_CFB, 2025)[17] == latest
    assert ranks_for_week(session, SPORT_CFB, 2025, 17, {}) == (latest, {})


def test_postseason_ranks_never_read_a_postseason_poll(session):
    """PS-M2: the week-17 poll row is ignored for display, so UGA is #2, not #25."""
    from app.services.predictions import poll_ranks_entering

    teams = _add_bowl_and_leaky_poll(session)
    assert poll_ranks_entering(session, SPORT_CFB, 2025, 17)[teams["UGA"].team_id] == 2
