"""SHAP explainability: top signed, human-labeled factors per prediction."""

import numpy as np
import pandas as pd
import shap

FEATURE_LABELS = {
    "elo_diff": "Team rating (Elo) edge",
    "epa_off_diff": "Offensive EPA/play, last 5 games",
    "epa_def_diff": "Defensive EPA/play allowed, last 5 games",
    "point_margin_diff": "Point differential, last 5 games",
    "win_pct_diff": "Win rate, last 5 games",
    "turnover_diff_diff": "Turnover differential, last 3 games",
    "rest_diff": "Rest advantage",
    "off_bye_diff": "Coming off a bye",
    "short_week_diff": "Short-week fatigue",
    "b2b_road_diff": "Back-to-back road games",
    "qb_out_diff": "Starting QB availability",
    "injury_sev_diff": "Overall injury burden",
    "is_divisional": "Divisional rivalry game",
    "is_primetime": "Primetime spotlight",
    "week_number": "Point in the season",
    "temp_f": "Kickoff temperature",
    "wind_mph": "Wind at kickoff",
    "precip": "Precipitation expected",
    "market_spread_home": "Vegas point spread",
    "market_home_prob": "Betting-market win probability",
}


def make_explainer(model) -> shap.TreeExplainer:
    return shap.TreeExplainer(model)


def top_factors(
    explainer: shap.TreeExplainer,
    row: pd.DataFrame,
    home_win_prob: float,
    n: int = 4,
) -> list[dict]:
    """Top-n features by |SHAP|. `value` is the approximate probability-space
    contribution; positive always means "toward the home team"."""
    shap_values = np.asarray(explainer.shap_values(row))[0]
    scale = home_win_prob * (1.0 - home_win_prob)
    order = np.argsort(-np.abs(shap_values))[:n]
    factors = []
    for idx in order:
        feature = row.columns[idx]
        value = float(shap_values[idx] * scale)
        factors.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "value": round(value, 4),
                "direction": "home" if value >= 0 else "away",
            }
        )
    return factors
