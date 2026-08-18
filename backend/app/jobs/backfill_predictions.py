"""Persist walk-forward predictions for completed seasons.

Each holdout season is scored by a model trained only on strictly prior
seasons, mirroring ml/backtest.py. The shipped artifact must not be used: it
trained on these seasons, so its accuracy on them would be in-sample.

Rows are stamped with a distinct model version so they are excluded from the
live record and can be labeled in the UI as reconstructed.

Usage: python -m app.jobs.backfill_predictions [--sport nfl|cfb]
"""

import argparse
from datetime import timedelta

import pandas as pd
from sqlalchemy import select

from app.db import session_scope
from app.jobs.predict_week import _as_utc
from app.models import SPORT_CFB, SPORT_NFL, Game, Prediction
from ml.backtest import SPORT_BACKTEST
from ml.features import training_frame
from ml.train import fbs_vs_fbs, fit_model, predict_calibrated


def backfill_version(sport: str) -> str:
    return "backtest-cfb-1.0.0" if sport.upper() == "CFB" else "backtest-1.0.0"


def walk_forward_predictions(
    df: pd.DataFrame, holdout_seasons: list[int], is_cfb: bool, week_split: int
) -> pd.DataFrame:
    """One row per scored game, from a model that never saw that season."""
    out = []
    for season in holdout_seasons:
        history = df[df["season"] < season]
        if history.empty:
            continue
        calib_season = int(history["season"].max())
        train_df = history[history["season"] < calib_season]
        calib_df = history[history["season"] == calib_season]
        if train_df.empty:
            # Single history season: split it by week instead.
            train_df = history[history["week"] <= week_split]
            calib_df = history[history["week"] > week_split]
        calib_fit_df = calib_df[fbs_vs_fbs(calib_df)] if is_cfb else None
        model, calibrator = fit_model(train_df, calib_df, calib_fit_df)

        holdout = df[df["season"] == season]
        probs = predict_calibrated(model, calibrator, holdout)
        out.append(
            pd.DataFrame(
                {
                    "game_id": holdout["game_id"].to_numpy(),
                    "season": season,
                    "home_win_prob": probs,
                }
            )
        )
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL
    cfg = SPORT_BACKTEST[sport]
    version = backfill_version(sport)
    holdout = cfg["holdout_seasons"]

    with session_scope() as db:
        df = training_frame(
            db, list(range(cfg["first_season"], holdout[-1] + 1)), sport=sport
        )
        preds = walk_forward_predictions(df, holdout, sport == SPORT_CFB, cfg["week_split"])
        if preds.empty:
            print(f"backfill ({args.sport}): nothing to write")
            return

        kickoffs = {
            g.game_id: (g.kickoff_time or g.game_date)
            for g in db.scalars(select(Game).where(Game.sport == sport))
        }
        existing = {
            p.game_id: p
            for p in db.scalars(
                select(Prediction).where(Prediction.model_version == version)
            )
        }
        written = 0
        for row in preds.itertuples(index=False):
            kickoff = kickoffs.get(row.game_id)
            if kickoff is None:
                continue
            pred = existing.get(row.game_id)
            if pred is None:
                pred = Prediction(game_id=row.game_id, model_version=version)
                db.add(pred)
                existing[row.game_id] = pred
            pred.home_win_prob = round(float(row.home_win_prob), 4)
            pred.shap_top_features = []
            pred.llm_narrative = None
            # Distinct, pre-kickoff timestamps: ties would make the
            # "latest prediction" ordering nondeterministic.
            pred.predicted_at = _as_utc(kickoff) - timedelta(hours=1)
            written += 1
        db.commit()

    print(f"backfill ({args.sport}): wrote {written} predictions as {version}")


if __name__ == "__main__":
    main()
