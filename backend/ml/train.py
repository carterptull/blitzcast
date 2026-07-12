"""Train the calibrated home-win-probability model and write the artifact.

Split is time-aware: the base XGBoost model trains on the earlier seasons,
the most recent season is the holdout used for early stopping and Platt
(sigmoid) calibration.

CFB trains the model on FBS-vs-FBS plus FBS-vs-FCS games, but fits the
calibrator (and reports headline metrics) on FBS-vs-FBS only — mismatch
outcomes are near-deterministic and would distort the reliability fit.

Usage: python -m ml.train [--sport nfl|cfb]
"""

import argparse
import json
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss
from xgboost import XGBClassifier

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL
from ml.calibration import PlattCalibrator
from ml.explain import feature_labels
from ml.features import FEATURE_COLUMNS, training_frame
from ml.model_store import artifacts_dir

TRAIN_SEASONS = [2022, 2023, 2024]
CALIB_SEASON = 2025

XGB_PARAMS = dict(
    max_depth=3,
    n_estimators=600,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=10,
    eval_metric="logloss",
    early_stopping_rounds=50,
)


def fbs_vs_fbs(df: pd.DataFrame) -> pd.Series:
    return (df["home_tier"] == "FBS") & (df["away_tier"] == "FBS")


def fit_model(
    train_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    calib_fit_df: pd.DataFrame | None = None,
) -> tuple[XGBClassifier, PlattCalibrator]:
    x_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["home_win"].astype(int)
    x_calib = calib_df[FEATURE_COLUMNS]
    y_calib = calib_df["home_win"].astype(int)

    model = XGBClassifier(**XGB_PARAMS)
    model.fit(x_train, y_train, eval_set=[(x_calib, y_calib)], verbose=False)

    fit_df = calib_df if calib_fit_df is None else calib_fit_df
    raw = model.predict_proba(fit_df[FEATURE_COLUMNS])[:, 1]
    calibrator = PlattCalibrator().fit(raw, fit_df["home_win"].astype(int).to_numpy())
    return model, calibrator


def predict_calibrated(model, calibrator, x: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(x[FEATURE_COLUMNS])[:, 1]
    return calibrator.transform(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL

    settings = get_settings()
    with session_scope() as db:
        df = training_frame(db, TRAIN_SEASONS + [CALIB_SEASON], sport=sport)

    train_df = df[df["season"].isin(TRAIN_SEASONS)]
    calib_df = df[df["season"] == CALIB_SEASON]
    calib_fit_df = calib_df[fbs_vs_fbs(calib_df)] if sport == SPORT_CFB else None
    print(f"training rows: {len(train_df)}, calibration rows: {len(calib_df)}")

    model, calibrator = fit_model(train_df, calib_df, calib_fit_df)

    eval_df = calib_df if calib_fit_df is None else calib_fit_df
    probs = predict_calibrated(model, calibrator, eval_df)
    y = eval_df["home_win"].astype(int).to_numpy()
    metrics = {
        "holdout_season": CALIB_SEASON,
        "brier": round(float(brier_score_loss(y, probs)), 4),
        "log_loss": round(float(log_loss(y, probs)), 4),
        "accuracy": round(float(((probs > 0.5) == y).mean()), 4),
        "best_iteration": int(model.best_iteration),
    }
    print("holdout metrics:", metrics)

    version = settings.model_version_for(sport)
    art_dir = artifacts_dir(sport)
    art_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = art_dir / f"model_{version}.joblib"
    joblib.dump(
        {
            "model": model,
            "calibrator": calibrator,
            "sport": sport,
            "feature_columns": FEATURE_COLUMNS,
            "feature_labels": feature_labels(sport),
            "training_window": {"train": TRAIN_SEASONS, "calibration": CALIB_SEASON},
            "metrics": metrics,
            "model_version": version,
            "trained_at": datetime.now(UTC).isoformat(),
        },
        artifact_path,
    )
    (art_dir / "latest.json").write_text(
        json.dumps({"model_version": version, "artifact": artifact_path.name}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {artifact_path}")


if __name__ == "__main__":
    main()
