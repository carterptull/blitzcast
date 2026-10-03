"""Batch prediction job: features -> predict_proba -> SHAP -> narrate ->
upsert predictions. Idempotent on (game_id, model_version); re-running
refreshes predictions with the latest inputs. Without --week it predicts the
default week plus every game kicking off within LOOKAHEAD_DAYS. It ends with a
coverage check and exits 1 if any game failed (after finishing the rest) or any
upcoming game lacks a prediction or booth section.

Usage: python -m app.jobs.predict_week [--season 2026] [--week N] [--sport nfl|cfb]
"""

import argparse
import logging
import re
import sys
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
from app.services.fact_sheet import GameFacts, build_game_facts, trusted_numbers_text
from app.services.fallback_narration import (
    fallback_narration,
    fallback_reason,
    minimal_narration,
)
from app.services.narrate import check_narration, narrate, reason_category
from app.services.predictions import poll_ranks_entering
from ml.explain import make_explainer, top_factors
from ml.features import build_features
from ml.model_store import load_latest

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=36)
LOOKAHEAD_DAYS = 7


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


def _failed(db: Session, game_id: str, step: str, exc: Exception) -> None:
    # Only the error type: messages can carry URLs or data.
    if isinstance(exc, SQLAlchemyError):
        db.rollback()
    logger.warning("%s failed for %s: %s", step, game_id, type(exc).__name__)


_PUNCTUATION_RE = re.compile("[\u2014\u2013;:]")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[.-]\d+)*")
_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(degrees|mph)\b", re.IGNORECASE)
_COIN_FLIP_RE = re.compile(r"\bcoin\s*flip|\btoss[\s-]?up\b", re.IGNORECASE)
_PRECIP_RE = re.compile(
    r"\b(?:rain\w*|snow\w*|sleet|showers?|drizzle|wet|soggy)\b", re.IGNORECASE
)
_WEATHER_RE = re.compile(
    r"\b(?:degrees|mph|wind\w*|gust\w*|weather|forecast|cold|chilly|freezing|frigid|icy"
    r"|hot|heat|humid\w*|indoors|dome|roof)\b",
    re.IGNORECASE,
)


def still_true(previous: str, facts: GameFacts) -> bool:
    """A stored narration may be republished only when it is exactly true
    against today's sheet, not merely close: every percentage is today's whole
    number, every other number (scores, records, degrees, lines, ranks, years)
    is on the trusted part of today's sheet (no venue or injury text), a coin
    flip is still 50%, weather talk is backed by today's weather, and the
    punctuation is plain. It must also pass check_narration, so the link,
    handle and digit-run rules apply too. Stricter than check_narration on
    purpose: a miss only costs a fresh template."""
    if _PUNCTUATION_RE.search(previous) or check_narration(previous, facts) is not None:
        return False
    p = facts.home_win_prob
    model_pcts = {round(p * 100), round((1 - p) * 100)}
    if any(float(m.group(1)) not in model_pcts for m in _PCT_RE.finditer(previous)):
        return False
    if _COIN_FLIP_RE.search(previous) and round(p * 100) != 50:
        return False
    sheet = " ".join(trusted_numbers_text(facts).split())
    on_sheet = set(_NUMBER_RE.findall(sheet))
    if any(n not in on_sheet for n in _NUMBER_RE.findall(_PCT_RE.sub(" ", previous))):
        return False
    units = {(n, u.lower()) for n, u in _UNIT_RE.findall(sheet)}
    if any((n, u.lower()) not in units for n, u in _UNIT_RE.findall(previous)):
        return False
    weather = facts.weather or ""
    if _PRECIP_RE.search(previous) and "rain or snow" not in weather:
        return False
    return not (_WEATHER_RE.search(previous) and not weather)


class Narration(NamedTuple):
    text: str | None
    source: str  # "llm", "kept", "fallback", "minimal" or "none"


def _minimal(db: Session, row: pd.Series, prob: float) -> Narration:
    try:
        return Narration(minimal_narration(row["home_abbr"], row["away_abbr"], prob), "minimal")
    except Exception as exc:
        _failed(db, row["game_id"], "minimal narration", exc)
        return Narration(None, "none")


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
    draft, else the previous narration only if it is still exactly true today,
    else the deterministic fallback from the fact sheet, else (no fact sheet, or
    a fallback that fails its check) a model-only line from the row. Rolling
    back is safe: since the last per-game commit the loop has only read."""
    game_id = row["game_id"]
    try:
        facts = facts_for_row(db, row, prob, factors, ranks, prev_ranks)
    except Exception as exc:
        _failed(db, game_id, "fact sheet", exc)
        return _minimal(db, row, prob)
    try:
        text = narrate(facts)
    except Exception as exc:
        _failed(db, game_id, "narration draft", exc)
        text = None
    if text:
        return Narration(text, "llm")
    if previous:
        try:
            if still_true(previous, facts):
                return Narration(previous, "kept")
        except Exception as exc:
            _failed(db, game_id, "previous narration check", exc)
    try:
        text = fallback_narration(facts)
        reason = fallback_reason(text, facts)
    except Exception as exc:
        _failed(db, game_id, "fallback narration", exc)
        return _minimal(db, row, prob)
    if reason is not None:
        logger.warning(
            "fallback narration rejected for %s: %s", game_id, reason_category(reason)
        )
        return _minimal(db, row, prob)
    return Narration(text, "fallback")


def narrate_and_store(
    db: Session,
    row: pd.Series,
    version: str,
    prob: float,
    factors: list,
    ranks: dict[int, int],
    prev_ranks: dict[int, int],
) -> Narration:
    previous = existing_narrative(db, row["game_id"], version)
    narration = narrate_safely(db, row, prob, factors, ranks, prev_ranks, previous=previous)
    upsert_prediction(db, row["game_id"], version, prob, factors, narration.text)
    return narration


def narration_summary(sources: Counter) -> list[str]:
    lines = [
        f"narration: {sources['llm']} written, {sources['kept']} kept, "
        f"{sources['fallback']} fallback, {sources['minimal']} minimal, {sources['none']} none"
    ]
    none = sources["none"]
    if none:
        games = "1 game has" if none == 1 else f"{none} games have"
        lines.append(f"WARNING: {games} no booth narration")
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


def select_target_ids(
    db: Session,
    season: int,
    sport: str,
    now: datetime | None = None,
    week: int | None = None,
    lookahead_days: int = LOOKAHEAD_DAYS,
) -> set[str]:
    """Unplayed, not-yet-kicked-off games to predict: an explicit week alone,
    else the default week plus any game kicking off within the look-ahead
    window. A TBD kickoff is judged by its game date."""
    now = now or datetime.now(UTC)
    if week is not None:
        return unplayed_game_ids(db, season, week, sport, now=now)
    base = default_week(db, season, sport, now=now)
    in_window = func.coalesce(Game.kickoff_time, Game.game_date) <= now + timedelta(
        days=lookahead_days
    )
    selected = in_window if base is None else (Game.week == base) | in_window
    rows = db.scalars(
        select(Game.game_id).where(
            Game.season == season,
            Game.sport == sport,
            Game.home_score.is_(None),
            Game.away_score.is_(None),
            (Game.kickoff_time.is_(None)) | (Game.kickoff_time > now),
            selected,
        )
    )
    return set(rows)


def ranks_for_week(
    db: Session,
    sport: str,
    season: int,
    week: int,
    cache: dict[int, dict[int, int]],
) -> tuple[dict[int, int], dict[int, int]]:
    """(ranks entering week, ranks entering the week before), each poll read once.
    A week with no published poll is {}, so the fact sheet prints no rank line."""

    def ranks(wk: int) -> dict[int, int]:
        if wk not in cache:
            cache[wk] = poll_ranks_entering(db, sport, season, wk)
        return cache[wk]

    # Both weeks resolve AP first, so the rank movement compares the same poll in practice.
    return ranks(week), (ranks(week - 1) if week > 1 else {})


class Predictor(NamedTuple):
    model: object
    calibrator: object
    explainer: object
    feature_columns: list[str]
    sport: str
    version: str


def predict_one(
    db: Session,
    row: pd.Series,
    predictor: Predictor,
    ranks: dict[int, int],
    prev_ranks: dict[int, int],
) -> Narration | None:
    """Predict, narrate, store and commit one game. Any failure is rolled back
    and logged by type only, and returns None so the rest of the slate runs."""
    game_id = row["game_id"]
    try:
        x = row[predictor.feature_columns].to_frame().T.astype(float)
        raw = predictor.model.predict_proba(x)[:, 1]
        prob = float(predictor.calibrator.transform(raw)[0])
        factors = top_factors(
            predictor.explainer,
            x,
            prob,
            sport=predictor.sport,
            market_available=bool(row["has_market_line"]),
            spread_available=bool(row["has_market_spread"]),
        )
        narration = narrate_and_store(
            db, row, predictor.version, prob, factors, ranks, prev_ranks
        )
        # Commit per game: a full CFB slate is ~100 sequential Claude calls,
        # and the upsert is idempotent, so partial progress is safe to keep.
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("prediction failed for %s: %s", game_id, type(exc).__name__)
        return None
    print(f"  {game_id}: home {prob:.1%} (narration: {narration.source})")
    return narration


def coverage_report(db: Session, season: int, sport: str, week: int | None) -> int:
    """Print the end-of-run coverage check and return its exit status. Imported
    late because app.jobs.coverage reads this module's selection."""
    from app.jobs.coverage import check_coverage, coverage_outcome

    lines, status = coverage_outcome(check_coverage(db, season, sport, week=week))
    for line in lines:
        print(line)
    return status


def _week_span(weeks: list[int]) -> str:
    lo, hi = min(weeks), max(weeks)
    return f"week {lo}" if lo == hi else f"weeks {lo}-{hi}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl", type=str.lower)
    args = parser.parse_args()
    sport = args.sport.upper()

    bundle = load_latest(sport=sport)
    model = bundle["model"]
    predictor = Predictor(
        model=model,
        calibrator=bundle["calibrator"],
        explainer=make_explainer(model),
        feature_columns=bundle["feature_columns"],
        sport=sport,
        version=get_settings().model_version_for(sport),
    )
    failed: list[str] = []

    with session_scope() as db:
        playable = select_target_ids(db, args.season, sport, week=args.week)
        if not playable:
            where = f"week {args.week}" if args.week is not None else "the look-ahead window"
            print(f"no unplayed {sport} games found for {args.season} {where}")
            return

        features = build_features(db, seasons=[args.season], sport=sport)
        if args.week is not None:
            in_week = features[features["week"] == args.week]
            skipped = len(in_week) - in_week["game_id"].isin(playable).sum()
            if skipped:
                print(f"skipping {skipped} already-final {sport} games")
        target = features[features["game_id"].isin(playable)]
        if target.empty:
            print(f"no unplayed {sport} games found for {args.season}")
            return

        span = _week_span([int(w) for w in target["week"]])
        print(f"predicting {len(target)} {sport} games for {args.season} {span}")
        poll_cache: dict[int, dict[int, int]] = {}
        sources: Counter = Counter()
        for _, row in target.iterrows():
            ranks, prev_ranks = ranks_for_week(db, sport, args.season, int(row["week"]), poll_cache)
            narration = predict_one(db, row, predictor, ranks, prev_ranks)
            if narration is None:
                failed.append(row["game_id"])
            else:
                sources[narration.source] += 1

        ok = len(target) - len(failed)
        print(f"predictions: {ok} ok, {len(failed)} failed")
        if failed:
            games = "1 game" if len(failed) == 1 else f"{len(failed)} games"
            print(f"WARNING: prediction failed for {games}: {', '.join(failed)}")
        for line in narration_summary(sources):
            print(line)
        gaps = coverage_report(db, args.season, sport, args.week)

    if failed or gaps:
        sys.exit(1)
    print("prediction batch complete")


if __name__ == "__main__":
    main()
