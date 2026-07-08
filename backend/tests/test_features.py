"""Leakage and feature-engineering correctness tests."""

import pandas as pd
from sqlalchemy import select

from app.models import Game
from ml.features import FEATURE_COLUMNS, build_features


def _feature_row(df: pd.DataFrame, game_id: str) -> pd.Series:
    row = df[df["game_id"] == game_id]
    assert len(row) == 1
    return row.iloc[0]


def test_no_leakage_from_kickoff_or_future(db):
    """Features for game G must not change when G's own result or any
    later result changes."""
    target = "2025_04_BUF_KC"
    before = _feature_row(build_features(db), target)[FEATURE_COLUMNS]

    # Flip the outcome of the target game and every game after it.
    games = db.scalars(select(Game).where(Game.season == 2025, Game.week >= 4)).all()
    for g in games:
        g.home_score, g.away_score = 0, 55
    db.flush()

    after = _feature_row(build_features(db), target)[FEATURE_COLUMNS]
    pd.testing.assert_series_equal(before, after, check_names=False)


def test_prior_results_do_change_features(db):
    """Sanity check the leakage test has teeth: changing a PRIOR game's
    result must change the target game's features."""
    target = "2025_04_BUF_KC"
    before = _feature_row(build_features(db), target)[FEATURE_COLUMNS]

    week1 = db.scalars(select(Game).where(Game.game_id == "2025_01_BUF_KC")).one()
    week1.home_score, week1.away_score = 0, 55
    db.flush()

    after = _feature_row(build_features(db), target)[FEATURE_COLUMNS]
    assert not before.equals(after)


def test_home_win_target(db):
    df = build_features(db)
    played = df[df["season"] == 2025]
    assert set(played["home_win"].unique()) == {0.0, 1.0}
    scheduled = df[df["season"] == 2026]
    assert scheduled["home_win"].isna().all()


def test_qb_out_flag_and_injury_severity_diff(db):
    df = build_features(db)
    row = _feature_row(df, "2026_01_BUF_KC")
    # BUF (away) QB is Out: home-minus-away qb_out diff is negative,
    # and away carries the injury burden.
    assert row["qb_out_diff"] == -1.0
    assert row["injury_sev_diff"] < 0


def test_market_features_present(db):
    df = build_features(db)
    row = _feature_row(df, "2026_01_BUF_KC")
    assert row["market_spread_home"] == 2.5
    assert 0.5 < row["market_home_prob"] < 1.0
