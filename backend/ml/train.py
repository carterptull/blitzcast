"""Train the calibrated home-win-probability model and write the artifact.

Split is time-aware: the base XGBoost model trains on the earlier seasons,
the most recent season is the holdout used for early stopping and Platt
(sigmoid) calibration.

Usage: python -m ml.train
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss
from xgboost import XGBClassifier

from app.config import get_settings
from app.db import session_scope
from ml.calibration import PlattCalibrator
from ml.explain import FEATURE_LABELS
from ml.features import FEATURE_COLUMNS, training_frame

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

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


def fit_model(
    train_df: pd.DataFrame, calib_df: pd.DataFrame
) -> tuple[XGBClassifier, PlattCalibrator]:
    x_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["home_win"].astype(int)
    x_calib = calib_df[FEATURE_COLUMNS]
    y_calib = calib_df["home_win"].astype(int)

    model = XGBClassifier(**XGB_PARAMS)
    model.fit(x_train, y_train, eval_set=[(x_calib, y_calib)], verbose=False)

    raw = model.predict_proba(x_calib)[:, 1]
    calibrator = PlattCalibrator().fit(raw, y_calib.to_numpy())
    return model, calibrator


def predict_calibrated(model, calibrator, x: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(x[FEATURE_COLUMNS])[:, 1]
    return calibrator.transform(raw)


def main() -> None:
    settings = get_settings()
    with session_scope() as db:
        df = training_frame(db, TRAIN_SEASONS + [CALIB_SEASON])

    train_df = df[df["season"].isin(TRAIN_SEASONS)]
    calib_df = df[df["season"] == CALIB_SEASON]
    print(f"training rows: {len(train_df)}, calibration rows: {len(calib_df)}")

    model, calibrator = fit_model(train_df, calib_df)

    probs = predict_calibrated(model, calibrator, calib_df)
    y = calib_df["home_win"].astype(int).to_numpy()
    metrics = {
        "holdout_season": CALIB_SEASON,
        "brier": round(float(brier_score_loss(y, probs)), 4),
        "log_loss": round(float(log_loss(y, probs)), 4),
        "accuracy": round(float(((probs > 0.5) == y).mean()), 4),
        "best_iteration": int(model.best_iteration),
    }
    print("holdout metrics:", metrics)

    version = settings.model_version
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS_DIR / f"model_{version}.joblib"
    joblib.dump(
        {
            "model": model,
            "calibrator": calibrator,
            "feature_columns": FEATURE_COLUMNS,
            "feature_labels": FEATURE_LABELS,
            "training_window": {"train": TRAIN_SEASONS, "calibration": CALIB_SEASON},
            "metrics": metrics,
            "model_version": version,
            "trained_at": datetime.now(UTC).isoformat(),
        },
        artifact_path,
    )
    (ARTIFACTS_DIR / "latest.json").write_text(
        json.dumps({"model_version": version, "artifact": artifact_path.name}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {artifact_path}")


if __name__ == "__main__":
    main()
