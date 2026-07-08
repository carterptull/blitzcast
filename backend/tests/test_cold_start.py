"""2026 cold-start: Week 1 predictions build without error and are not
degenerate (not all 50/50), because Elo carries forward and prior-season
form seeds the rolling windows."""

import numpy as np

from ml.calibration import PlattCalibrator
from ml.features import FEATURE_COLUMNS, build_features
from ml.train import XGB_PARAMS


def test_week1_features_have_signal(db):
    df = build_features(db, seasons=[2026])
    assert len(df) == 2
    assert df[FEATURE_COLUMNS].notna().all().all()
    # Elo carried forward from 2025 gives KC (6-0 at home) a real edge.
    kc = df[df["game_id"] == "2026_01_BUF_KC"].iloc[0]
    assert kc["elo_diff"] > 0
    # Rolling form seeded from late-2025 games, not empty.
    assert kc["epa_off_diff"] != 0
    assert kc["market_home_prob"] is not None


def test_week1_predictions_not_degenerate(db):
    df = build_features(db)
    train = df[df["home_win"].notna()]
    target = df[df["season"] == 2026]

    from xgboost import XGBClassifier

    params = dict(XGB_PARAMS)
    params.pop("early_stopping_rounds")
    params["n_estimators"] = 30
    model = XGBClassifier(**params)
    x = train[FEATURE_COLUMNS]
    y = train["home_win"].astype(int)
    model.fit(x, y, verbose=False)

    raw_train = model.predict_proba(x)[:, 1]
    calibrator = PlattCalibrator().fit(raw_train, y.to_numpy())

    raw = model.predict_proba(target[FEATURE_COLUMNS])[:, 1]
    probs = calibrator.transform(raw)
    assert np.isfinite(probs).all()
    assert (probs > 0.0).all() and (probs < 1.0).all()
    # Not all coin flips.
    assert not np.allclose(probs, 0.5, atol=0.01)
