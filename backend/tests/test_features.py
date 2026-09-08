"""Leakage and feature-engineering correctness tests."""

import pandas as pd
from sqlalchemy import select

from app.models import Game
from ml.features import FEATURE_COLUMNS, build_features, market_home_prob


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


def test_market_home_prob_ignores_no_quote_sentinel():
    """CFBD returns -100000 as a "no real price quoted" marker on the
    extreme side of lopsided blowouts, not a genuine moneyline (see
    cfb_401856665, a 57-0 game where both sides were -100000). Treating it
    as real corrupts the de-vigged probability toward 0.5 for a blowout;
    it must fall back to the spread instead."""
    # Both sides sentinel: no usable moneyline at all, fall back to spread.
    assert market_home_prob(-100000, -100000, -30.0) == market_home_prob(
        None, None, -30.0
    )
    # One real, one sentinel (cfb_401856780: WVU -1725, CCU -100000):
    # falls back to spread rather than averaging a real quote with a
    # placeholder as if both were genuine prices.
    assert market_home_prob(-1725, -100000, 20.0) == market_home_prob(
        None, None, 20.0
    )
    # Two genuine, merely large, favorites are untouched.
    assert market_home_prob(-1725, 900, None) is not None
    assert 0.5 < market_home_prob(-1725, 900, None) < 1.0
