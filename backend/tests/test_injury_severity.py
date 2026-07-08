import pandas as pd

from ml.features import (
    POSITION_WEIGHTS,
    STATUS_WEIGHTS,
    injury_severity,
)


def _frame(rows):
    return pd.DataFrame(rows, columns=["position", "status"])


def test_qb_out_dominates_depth_players():
    qb = injury_severity(_frame([("QB", "Out")]))
    two_backups = injury_severity(_frame([("LS", "Out"), ("P", "Out")]))
    assert qb > two_backups * 2


def test_status_weighting():
    out = injury_severity(_frame([("WR", "Out")]))
    questionable = injury_severity(_frame([("WR", "Questionable")]))
    assert out == POSITION_WEIGHTS["WR"] * STATUS_WEIGHTS["out"]
    assert questionable == POSITION_WEIGHTS["WR"] * STATUS_WEIGHTS["questionable"]
    assert out > questionable


def test_unknown_status_scores_zero():
    assert injury_severity(_frame([("QB", "Probable")])) == 0.0
    assert injury_severity(_frame([("QB", None)])) == 0.0


def test_unknown_position_gets_default_weight():
    sev = injury_severity(_frame([("XX", "Out")]))
    assert sev == 1.0


def test_sum_over_players():
    sev = injury_severity(_frame([("QB", "Out"), ("CB", "Questionable")]))
    expected = POSITION_WEIGHTS["QB"] + POSITION_WEIGHTS["CB"] * 0.4
    assert sev == expected
