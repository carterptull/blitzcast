"""Verdict rule. Three distinct null cases, all real."""

import pytest

from app.services.predictions import prediction_verdict


@pytest.mark.parametrize(
    "prob, home, away, expected",
    [
        (0.62, 27, 24, True),    # favored home won
        (0.62, 24, 27, False),   # favored home lost
        (0.38, 24, 27, True),    # favored away won
        (0.38, 27, 24, False),   # favored away lost
        (None, 27, 24, None),    # no prediction
        (0.62, 24, 24, None),    # tie
        (0.5, 27, 24, None),     # no pick
        (0.62, None, None, None),  # not played
        (0.62, 27, None, None),    # half-scored row is not final
    ],
)
def test_prediction_verdict(prob, home, away, expected):
    assert prediction_verdict(prob, home, away) is expected
