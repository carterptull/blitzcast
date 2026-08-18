"""Temporal-disjointness guard for train/calibration split."""

import pandas as pd
import pytest


def test_training_rows_must_precede_the_calibration_set():
    from ml.train import assert_temporally_disjoint

    train = pd.DataFrame({"kickoff": pd.to_datetime(["2024-09-01", "2024-10-01"], utc=True)})
    calib = pd.DataFrame({"kickoff": pd.to_datetime(["2025-09-01"], utc=True)})
    assert_temporally_disjoint(train, calib)  # no raise

    overlapping = pd.DataFrame({"kickoff": pd.to_datetime(["2025-10-01"], utc=True)})
    with pytest.raises(ValueError, match="overlap"):
        assert_temporally_disjoint(overlapping, calib)
