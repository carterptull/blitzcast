"""market_spread_home / market_home_prob are checkable facts (which team
the market favors) -- their displayed direction must match the raw value,
not the model's local SHAP attribution, which can point the other way for
small/near-toss-up lines (see cfb_401856682, OSU@TEX, Week 2 2026:
market_spread_home=+1.5 favors the home team, but that feature's SHAP
contribution was locally negative)."""
import numpy as np
import pandas as pd

from ml.explain import top_factors


class _FakeExplainer:
    def __init__(self, values):
        self._values = values

    def shap_values(self, row):
        return np.array([self._values])


def test_market_spread_direction_follows_raw_value_not_shap_sign():
    row = pd.DataFrame([{
        "market_spread_home": 1.5,   # positive = home favored
        "market_home_prob": 0.517,   # >0.5 = home favored
        "elo_diff": -41.1,
    }])
    # SHAP says "away" for both market features (the reproduced real bug);
    # elo_diff SHAP is genuinely negative too and has no ground truth to
    # override, so it must stay "away".
    shap_values = [-0.12, -0.04, -0.02]
    explainer = _FakeExplainer(shap_values)
    factors = top_factors(explainer, row, home_win_prob=0.45, n=3, sport="CFB")
    by_feature = {f["feature"]: f for f in factors}
    assert by_feature["market_spread_home"]["direction"] == "home"
    assert by_feature["market_home_prob"]["direction"] == "home"
    assert by_feature["elo_diff"]["direction"] == "away"


def test_market_spread_negative_still_favors_away():
    row = pd.DataFrame([{"market_spread_home": -3.0, "market_home_prob": 0.4}])
    shap_values = [0.05, 0.05]  # even if SHAP disagreed, raw value wins
    explainer = _FakeExplainer(shap_values)
    factors = top_factors(explainer, row, home_win_prob=0.4, n=2, sport="NFL")
    by_feature = {f["feature"]: f for f in factors}
    assert by_feature["market_spread_home"]["direction"] == "away"
    assert by_feature["market_home_prob"]["direction"] == "away"


def test_market_factors_are_skipped_when_no_line_exists():
    row = pd.DataFrame([{"market_spread_home": 4.0, "market_home_prob": 0.6, "elo_diff": 80.0}])
    explainer = _FakeExplainer([0.30, 0.20, 0.05])
    factors = top_factors(explainer, row, home_win_prob=0.7, n=3, market_available=False)
    assert [f["feature"] for f in factors] == ["elo_diff"]


def _market_row():
    return pd.DataFrame([{"market_spread_home": 4.0, "market_home_prob": 0.6, "elo_diff": 80.0}])


def test_derived_spread_is_skipped_but_moneyline_prob_kept():
    explainer = _FakeExplainer([0.30, 0.20, 0.05])
    factors = top_factors(
        explainer, _market_row(), home_win_prob=0.7, n=3, spread_available=False
    )
    assert [f["feature"] for f in factors] == ["market_home_prob", "elo_diff"]


def test_no_market_line_still_drops_both_market_factors():
    explainer = _FakeExplainer([0.30, 0.20, 0.05])
    factors = top_factors(
        explainer, _market_row(), home_win_prob=0.7, n=3,
        market_available=False, spread_available=True,
    )
    assert [f["feature"] for f in factors] == ["elo_diff"]


def test_market_factors_default_to_available():
    explainer = _FakeExplainer([0.30, 0.20, 0.05])
    factors = top_factors(explainer, _market_row(), home_win_prob=0.7, n=3)
    assert [f["feature"] for f in factors] == [
        "market_spread_home", "market_home_prob", "elo_diff",
    ]
