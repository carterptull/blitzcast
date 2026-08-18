"""Backfilled predictions are labeled and never pollute the live record."""

from app.jobs.backfill_predictions import backfill_version


def test_backfill_version_is_distinct_per_sport():
    assert backfill_version("NFL") == "backtest-1.0.0"
    assert backfill_version("CFB") == "backtest-cfb-1.0.0"


def test_backfill_version_never_collides_with_live_versions():
    """The record query excludes anything starting with 'backtest'."""
    for sport in ("NFL", "CFB"):
        assert backfill_version(sport).startswith("backtest")
