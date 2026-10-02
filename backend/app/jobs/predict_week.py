"""Batch prediction job: features -> predict_proba -> SHAP -> narrate ->
upsert predictions. Idempotent on (game_id, model_version); re-running
refreshes predictions with the latest inputs.

Usage: python -m app.jobs.predict_week [--season 2026] [--week N] [--sport nfl|cfb]
"""

import argparse
import logging
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import NamedTuple

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_NFL, Game, Prediction
from app.services.fact_sheet import GameFacts, build_game_facts
from app.services.fallback_narration import fallback_narration
from app.services.narrate import check_narration, narrate
from app.services.predictions import poll_ranks_entering
from ml.explain import make_explainer, top_factors
from ml.features import build_features
from ml.model_store import load_latest

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=36)


def _as_utc(value) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.combine(value, time.min)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def default_week(
    db: Session, season: int, sport: str = SPORT_NFL, now: datetime | None = None
) -> int | None:
    """Earliest week that still has a game to play.

    A week whose last kickoff is well past is treated as done even if a game
    never received a score, so a cancellation cannot pin the job forever."""
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(Game.week, func.max(func.coalesce(Game.kickoff_time, Game.game_date)))
        .where(
            Game.season == season,
            Game.sport == sport,
            Game.home_score.is_(None),
            Game.away_score.is_(None),
        )
        .group_by(Game.week)
        .order_by(Game.week)
    ).all()
    for week, last_kickoff in rows:
        if last_kickoff is None:
            return week
        if _as_utc(last_kickoff) + STALE_AFTER > now:
            return week
    return None


def _stored_prediction(db: Session, game_id: str, version: str) -> Prediction | None:
    return db.scalar(
        select(Prediction).where(
            Prediction.game_id == game_id, Prediction.model_version == version
        )
    )


def existing_narrative(db: Session, game_id: str, version: str) -> str | None:
    stored = _stored_prediction(db, game_id, version)
    return stored.llm_narrative if stored is not None else None


def upsert_prediction(
    db: Session, game_id: str, version: str, prob: float, factors: list, narrative: str | None
) -> None:
    existing = _stored_prediction(db, game_id, version)
    if existing is None:
        existing = Prediction(game_id=game_id, model_version=version)
        db.add(existing)
    existing.home_win_prob = round(float(prob), 4)
    existing.shap_top_features = factors
    existing.llm_narrative = narrative
    existing.predicted_at = datetime.now(UTC)


def facts_for_row(
    db: Session,
    row: pd.Series,
    prob: float,
    factors: list,
    ranks: dict[int, int],
    prev_ranks: dict[int, int],
) -> GameFacts:
    """Narration input. Only a posted spread is narrated as the betting line; a
    moneyline-derived or Elo-derived one never reaches it."""
    game = db.get(Game, row["game_id"])
    has_spread = bool(row.get("has_market_spread", 1.0))
    spread = float(row["market_spread_home"]) if has_spread else None
    return build_game_facts(db, game, prob, factors, spread, ranks, prev_ranks)


def _skip(db: Session, game_id: str, step: str, exc: Exception) -> None:
    # Only the error type: messages can carry URLs or data.
    if isinstance(exc, SQLAlchemyError):
        db.rollback()
    logger.warning("%s skipped for %s: %s", step, game_id, type(exc).__name__)


class Narration(NamedTuple):
    text: str | None
    source: str  # "llm", "kept", "fallback" or "none"


def narrate_safely(
    db: Session,
    row: pd.Series,
    prob: float,
    factors: list,
    ranks: dict[int, int],
    prev_ranks: dict[int, int],
    previous: str | None = None,
) -> Narration:
    """Fact-sheet building and narration may fail for one game without costing
    that game, or the rest of the slate, its prediction. The chain: a fresh AI
    draft, else the previous narration if it still passes today's fact check,
    else the deterministic fallback. Without a fact sheet there is nothing true
    to say. Rolling back is safe: since the last per-game commit the loop has
    only read."""
    game_id = row["game_id"]
    try:
        facts = facts_for_row(db, row, prob, factors, ranks, prev_ranks)
    except Exception as exc:
        _skip(db, game_id, "narration", exc)
        return Narration(None, "none")
    try:
        text = narrate(facts)
    except Exception as exc:
        _skip(db, game_id, "narration", exc)
        text = None
    if text:
        return Narration(text, "llm")
    if previous:
        try:
            if check_narration(previous, facts) is None:
                return Narration(previous, "kept")
        except Exception as exc:
            _skip(db, game_id, "previous narration check", exc)
    try:
        text = fallback_narration(facts)
        reason = check_narration(text, facts)
    except Exception as exc:
        _skip(db, game_id, "fallback narration", exc)
        return Narration(None, "none")
    if reason is not None:
        logger.warning("fallback narration rejected for %s: %s", game_id, reason)
        return Narration(None, "none")
    return Narration(text, "fallback")


def narration_summary(sources: Counter) -> list[str]:
    lines = [
        f"narration: {sources['llm']} written, {sources['kept']} kept, "
        f"{sources['fallback']} fallback, {sources['none']} none"
    ]
    if sources["none"]:
        lines.append(f"WARNING: {sources['none']} games have no booth narration")
    return lines


def unplayed_game_ids(
    db: Session, season: int, week: int, sport: str, now: datetime | None = None
) -> set[str]:
    """Game ids in the week with no score yet and no kickoff in the past.
    Both scores must be absent: a row with one side scored has started, and
    re-predicting it would restamp predicted_at after the result was known.
    A past kickoff excludes it too, even with both scores still NULL: a game
    already underway (or one whose final score just hasn't landed yet) would
    otherwise get re-predicted with identical pre-game inputs but a
    predicted_at that lies about when the call was actually made. A NULL
    kickoff is a still-TBD future game and stays eligible regardless of
    `now`."""
    now = now or datetime.now(UTC)
    rows = db.scalars(
        select(Game.game_id).where(
            Game.season == season,
            Game.sport == sport,
            Game.week == week,
            Game.home_score.is_(None),
            Game.away_score.is_(None),
            (Game.kickoff_time.is_(None)) | (Game.kickoff_time > now),
        )
    )
    return set(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl", type=str.lower)
    args = parser.parse_args()
    sport = args.sport.upper()

    bundle = load_latest(sport=sport)
    model = bundle["model"]
    calibrator = bundle["calibrator"]
    feature_columns = bundle["feature_columns"]
    version = get_settings().model_version_for(sport)
    explainer = make_explainer(model)

    with session_scope() as db:
        week = args.week if args.week is not None else default_week(db, args.season, sport)
        if week is None:
            print(f"no unplayed {sport} games found for season {args.season}")
            return

        features = build_features(db, seasons=[args.season], sport=sport)
        target = features[features["week"] == week]
        playable = unplayed_game_ids(db, args.season, week, sport)
        skipped = len(target) - target["game_id"].isin(playable).sum()
        target = target[target["game_id"].isin(playable)]
        if skipped:
            print(f"skipping {skipped} already-final {sport} games")
        if target.empty:
            print(f"no unplayed {sport} games found for {args.season} week {week}")
            return

        ranks = poll_ranks_entering(db, sport, args.season, week)
        # Both weeks resolve AP first, so the rank movement compares the same poll in practice.
        prev_ranks = poll_ranks_entering(db, sport, args.season, week - 1) if week > 1 else {}
        print(f"predicting {len(target)} {sport} games for {args.season} week {week}")
        sources: Counter = Counter()

        for _, row in target.iterrows():
            x = row[feature_columns].to_frame().T.astype(float)
            raw = model.predict_proba(x)[:, 1]
            prob = float(calibrator.transform(raw)[0])
            factors = top_factors(
                explainer,
                x,
                prob,
                sport=sport,
                market_available=bool(row["has_market_line"]),
                spread_available=bool(row["has_market_spread"]),
            )

            previous = existing_narrative(db, row["game_id"], version)
            narration = narrate_safely(
                db, row, prob, factors, ranks, prev_ranks, previous=previous
            )
            sources[narration.source] += 1

            upsert_prediction(db, row["game_id"], version, prob, factors, narration.text)
            # Commit per game: a full CFB slate is ~100 sequential Claude calls,
            # and the upsert is idempotent, so partial progress is safe to keep.
            db.commit()
            print(f"  {row['game_id']}: home {prob:.1%} (narration: {narration.source})")

        for line in narration_summary(sources):
            print(line)

    print("prediction batch complete")


if __name__ == "__main__":
    main()
