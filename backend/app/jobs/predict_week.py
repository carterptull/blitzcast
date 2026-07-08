"""Batch prediction job: features -> predict_proba -> SHAP -> narrate ->
upsert predictions. Idempotent on (game_id, model_version); re-running
refreshes predictions with the latest inputs.

Usage: python -m app.jobs.predict_week [--season 2026] [--week N]
"""

import argparse
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Game, Prediction, Team
from app.services.narrate import narrate
from ml.explain import make_explainer, top_factors
from ml.features import build_features
from ml.model_store import load_latest


def default_week(db: Session, season: int) -> int | None:
    """Earliest week in the season with an unplayed game."""
    week = db.scalar(
        select(Game.week)
        .where(Game.season == season, Game.home_score.is_(None))
        .order_by(Game.week)
        .limit(1)
    )
    return week


def upsert_prediction(
    db: Session, game_id: str, version: str, prob: float, factors: list, narrative: str | None
) -> None:
    existing = db.scalar(
        select(Prediction).where(
            Prediction.game_id == game_id, Prediction.model_version == version
        )
    )
    if existing is None:
        existing = Prediction(game_id=game_id, model_version=version)
        db.add(existing)
    existing.home_win_prob = round(float(prob), 4)
    existing.shap_top_features = factors
    existing.llm_narrative = narrative
    existing.predicted_at = datetime.now(UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=None)
    args = parser.parse_args()

    bundle = load_latest()
    model = bundle["model"]
    calibrator = bundle["calibrator"]
    feature_columns = bundle["feature_columns"]
    version = bundle["model_version"]
    explainer = make_explainer(model)

    with session_scope() as db:
        week = args.week if args.week is not None else default_week(db, args.season)
        if week is None:
            print(f"no unplayed games found for season {args.season}")
            return

        features = build_features(db, seasons=[args.season])
        target = features[features["week"] == week]
        if target.empty:
            print(f"no games found for {args.season} week {week}")
            return

        team_names = {t.abbr: t.name for t in db.scalars(select(Team))}
        print(f"predicting {len(target)} games for {args.season} week {week}")

        for _, row in target.iterrows():
            x = row[feature_columns].to_frame().T.astype(float)
            raw = model.predict_proba(x)[:, 1]
            prob = float(calibrator.transform(raw)[0])
            factors = top_factors(explainer, x, prob)

            spread = row["market_spread_home"]
            narrative = narrate(
                {
                    "home_name": team_names.get(row["home_abbr"], row["home_abbr"]),
                    "home_abbr": row["home_abbr"],
                    "away_name": team_names.get(row["away_abbr"], row["away_abbr"]),
                    "away_abbr": row["away_abbr"],
                    "home_win_prob": prob,
                    "factors": factors,
                    "spread_home": None if pd.isna(spread) else float(spread),
                }
            )

            upsert_prediction(db, row["game_id"], version, prob, factors, narrative)
            print(
                f"  {row['game_id']}: home {prob:.1%}"
                + (" (narrated)" if narrative else " (no narrative)")
            )

    print("prediction batch complete")


if __name__ == "__main__":
    main()
