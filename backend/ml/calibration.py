"""Probability calibration for the base model."""

import numpy as np
from sklearn.linear_model import LogisticRegression


class PlattCalibrator:
    """Sigmoid calibration on the base model's log-odds."""

    def __init__(self) -> None:
        self._lr = LogisticRegression(C=1e6, solver="lbfgs")

    @staticmethod
    def _logit(p: np.ndarray) -> np.ndarray:
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(self, raw_probs: np.ndarray, y: np.ndarray) -> "PlattCalibrator":
        self._lr.fit(self._logit(raw_probs), y)
        return self

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        return self._lr.predict_proba(self._logit(raw_probs))[:, 1]
