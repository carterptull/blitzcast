"""Coverage check: upcoming games with no live prediction or no booth section.
Read-only. Shares its window and model version with predict_week, so it audits
exactly the rows that job is meant to write; exits 1 when any gap exists.

Usage: python -m app.jobs.coverage [--season 2026] [--sport nfl|cfb]
"""

import argparse
import sys
from datetime import datetime
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.jobs.predict_week import LOOKAHEAD_DAYS, select_target_ids
from app.models import Prediction


class Gap(NamedTuple):
    game_id: str
    missing: str  # "prediction" or "narration"


class Coverage(NamedTuple):
    upcoming: int
    gaps: list[Gap]


def check_coverage(
    db: Session,
    season: int,
    sport: str,
    version: str | None = None,
    now: datetime | None = None,
    lookahead_days: int = LOOKAHEAD_DAYS,
    week: int | None = None,
) -> Coverage:
    """A live prediction is any row not stamped as a backtest (or, with
    `version`, that version only); narration is judged on the latest one."""
    ids = select_target_ids(
        db, season, sport, now=now, week=week, lookahead_days=lookahead_days
    )
    if not ids:
        return Coverage(0, [])
    query = (
        select(Prediction)
        .where(
            Prediction.game_id.in_(ids),
            ~Prediction.model_version.startswith("backtest"),
        )
        .order_by(Prediction.predicted_at, Prediction.prediction_id)
    )
    if version is not None:
        query = query.where(Prediction.model_version == version)
    latest = {p.game_id: p for p in db.scalars(query)}
    gaps = []
    for game_id in sorted(ids):
        prediction = latest.get(game_id)
        if prediction is None:
            gaps.append(Gap(game_id, "prediction"))
        elif not (prediction.llm_narrative or "").strip():
            gaps.append(Gap(game_id, "narration"))
    return Coverage(len(ids), gaps)


def coverage_gaps(
    db: Session,
    season: int,
    sport: str,
    version: str | None = None,
    now: datetime | None = None,
    lookahead_days: int = LOOKAHEAD_DAYS,
    week: int | None = None,
) -> list[Gap]:
    return check_coverage(db, season, sport, version, now, lookahead_days, week).gaps


def coverage_outcome(coverage: Coverage) -> tuple[list[str], int]:
    """The log lines and the process exit status for a coverage result."""
    no_prediction = [g.game_id for g in coverage.gaps if g.missing == "prediction"]
    no_booth = [g.game_id for g in coverage.gaps if g.missing == "narration"]
    lines = [
        f"coverage: {coverage.upcoming} upcoming games, {len(no_prediction)} missing a "
        f"prediction, {len(no_booth)} missing a booth section"
    ]
    if no_prediction:
        lines.append(f"WARNING: no prediction for {', '.join(no_prediction)}")
    if no_booth:
        lines.append(f"WARNING: no booth section for {', '.join(no_booth)}")
    return lines, int(bool(coverage.gaps))


def current_version(sport: str) -> str | None:
    """The version predict_week stamps for `sport`, read from settings (no model
    file needed), or None when it cannot be resolved."""
    try:
        return get_settings().model_version_for(sport)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl", type=str.lower)
    args = parser.parse_args()
    sport = args.sport.upper()
    version = current_version(sport)
    if version is None:
        print(f"coverage: no current model version for {sport}, counting any live prediction")

    with session_scope() as db:
        lines, status = coverage_outcome(check_coverage(db, args.season, sport, version=version))
    for line in lines:
        print(line)
    if status:
        sys.exit(status)


if __name__ == "__main__":
    main()
