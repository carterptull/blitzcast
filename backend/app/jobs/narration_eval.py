"""Measure narration quality without writing anything.

Usage: python -m app.jobs.narration_eval --sport nfl --week 4
       [--season 2026] [--limit 20] [--stored | --spend-tokens]

--stored re-checks each game's saved narration against today's guardrail
(free, no API calls). Without it, fresh narrations are generated, which
spends Anthropic tokens and needs --spend-tokens. Every mode also checks that
the deterministic fallback passes the guardrail, and exits 1 if it does not.
The DB is only read: the session is rolled back and never committed.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.jobs.predict_week import facts_for_row
from app.models import Prediction
from app.services.fact_sheet import GameFacts
from app.services.fallback_narration import fallback_narration
from app.services.narrate import NarrationResult, check_narration, generate
from app.services.narrate import reason_category as narration_reason_category
from app.services.predictions import poll_ranks_entering
from ml.features import build_features

NO_NARRATION = "no narration stored"
FACTS_ERROR = "fact sheet failed"

def reason_category(reason: str) -> str:
    """A fixed label for a rejection, including this script's own two."""
    if reason in (NO_NARRATION, FACTS_ERROR):
        return reason
    return narration_reason_category(reason)


def summarize(results: list[tuple[str, NarrationResult]]) -> dict:
    reasons = Counter(reason_category(r) for _, res in results for r in res.rejections)
    passed = [res for _, res in results if res.text]
    return {
        "games": len(results),
        "passed": len(passed),
        "mean_attempts": sum(res.attempts for _, res in results) / max(len(results), 1),
        "mean_words": sum(len(res.text.split()) for res in passed) / max(len(passed), 1),
        "reasons": dict(reasons),
    }


@contextmanager
def _read_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _fallback_ok(facts: GameFacts) -> bool:
    try:
        return check_narration(fallback_narration(facts), facts) is None
    except Exception:
        return False


def _latest_live_prediction(db: Session, game_id: str) -> Prediction | None:
    return db.scalars(
        select(Prediction)
        .where(Prediction.game_id == game_id, ~Prediction.model_version.like("backtest%"))
        .order_by(Prediction.predicted_at.desc())
    ).first()


def _stored_result(text: str | None, facts: GameFacts) -> NarrationResult:
    if not text:
        return NarrationResult(text=None, attempts=1, rejections=[NO_NARRATION])
    reason = check_narration(text, facts)
    if reason is None:
        return NarrationResult(text=text, attempts=1)
    return NarrationResult(text=None, attempts=1, rejections=[reason_category(reason)])


def _line(game_id: str, res: NarrationResult, stored: bool, fallback_ok: bool) -> str:
    cats = ", ".join(dict.fromkeys(reason_category(r) for r in res.rejections))
    if stored:
        if res.text:
            status = "stored=pass"
        elif cats == NO_NARRATION:
            status = "stored=none"
        else:
            status = f"stored=fail ({cats})"
    else:
        status = f"attempts={res.attempts} result={'pass' if res.text else 'fail'}"
        if cats:
            status += f" ({cats})"
    return f"{game_id} {status} fallback={'pass' if fallback_ok else 'FAIL'}"


def evaluate(
    db: Session, sport: str, season: int, week: int, limit: int, stored: bool
) -> tuple[list[tuple[str, NarrationResult]], dict[str, bool]]:
    """Per-game narration results, and whether the fallback passed for each game."""
    features = build_features(db, seasons=[season], sport=sport)
    target = features[features["week"] == week].head(limit)
    ranks = poll_ranks_entering(db, sport, season, week)
    prev = poll_ranks_entering(db, sport, season, week - 1) if week > 1 else {}
    results: list[tuple[str, NarrationResult]] = []
    fallback: dict[str, bool] = {}
    for _, row in target.iterrows():
        game_id = row["game_id"]
        pred = _latest_live_prediction(db, game_id)
        if pred is None:
            continue
        try:
            facts = facts_for_row(
                db, row, pred.home_win_prob, pred.shap_top_features or [], ranks, prev
            )
        except Exception as exc:
            if isinstance(exc, SQLAlchemyError):
                db.rollback()  # else every later game fails on the aborted transaction
            print(f"{game_id} {FACTS_ERROR} ({type(exc).__name__})")
            results.append((game_id, NarrationResult(None, 0, [FACTS_ERROR])))
            continue
        fallback[game_id] = _fallback_ok(facts)
        res = _stored_result(pred.llm_narrative, facts) if stored else generate(facts)
        results.append((game_id, res))
        print(_line(game_id, res, stored, fallback[game_id]))
        if res.text:
            print(f"  {res.text}")
    return results, fallback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl", type=str.lower)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--stored", action="store_true")
    parser.add_argument("--spend-tokens", action="store_true")
    args = parser.parse_args(argv)

    if not args.stored:
        print("Fresh generation spends Anthropic tokens (up to 3 calls per game).")
        if not args.spend_tokens:
            print("Re-run with --spend-tokens to proceed, or use --stored (free).")
            return 2

    with _read_session() as db:
        results, fallback = evaluate(
            db, args.sport.upper(), args.season, args.week, args.limit, args.stored
        )

    s = summarize(results)
    parts = [
        f"games={s['games']}",
        f"passed={s['passed']}",
        f"pass_rate={s['passed'] / max(s['games'], 1):.0%}",
    ]
    if not args.stored:
        parts.append(f"mean_attempts={s['mean_attempts']:.2f}")
    parts += [
        f"mean_words={s['mean_words']:.1f}",
        f"reasons={s['reasons']}",
        f"fallback_passed={sum(fallback.values())}/{len(fallback)}",
    ]
    print("\nsummary: " + " ".join(parts))
    failed = [game_id for game_id, ok in fallback.items() if not ok]
    if failed:
        print("BUG: fallback narration failed the guardrail for " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
