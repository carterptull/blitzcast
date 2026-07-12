"""Batch prediction job: features -> predict_proba -> SHAP -> narrate ->
upsert predictions. Idempotent on (game_id, model_version); re-running
refreshes predictions with the latest inputs.

Usage: python -m app.jobs.predict_week [--season 2026] [--week N] [--sport nfl|cfb]
"""

import argparse
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL, Game, Prediction, Team
from app.services.narrate import narrate
from app.services.predictions import poll_ranks_entering
from ml.explain import make_explainer, top_factors
from ml.features import build_features
from ml.model_store import load_latest


def default_week(db: Session, season: int, sport: str = SPORT_NFL) -> int | None:
    """Earliest week in the season with an unplayed game.

    Keyed on missing score only, so TBD (NULL) kickoffs are never dropped."""
    week = db.scalar(
        select(Game.week)
        .where(Game.season == season, Game.sport == sport, Game.home_score.is_(None))
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


def _rank_phrase(name: str, rank: int | None) -> str:
    return f"{name} ranked #{rank}" if rank else f"{name} unranked"


def build_narration_payload(
    row: pd.Series,
    prob: float,
    factors: list,
    teams_by_abbr: dict[str, Team],
    sport: str,
    ranks: dict[int, int] | None = None,
) -> dict:
    """Narration input. CFB adds poll/conference color keys and carries no
    QB/injury note (no standardized CFB injury report to cite)."""
    home = teams_by_abbr.get(row["home_abbr"])
    away = teams_by_abbr.get(row["away_abbr"])
    spread = row.get("market_spread_home")
    payload = {
        "sport": sport,
        "home_name": home.name if home else row["home_abbr"],
        "home_abbr": row["home_abbr"],
        "away_name": away.name if away else row["away_abbr"],
        "away_abbr": row["away_abbr"],
        "home_win_prob": prob,
        "factors": factors,
        "spread_home": None if spread is None or pd.isna(spread) else float(spread),
    }
    if sport == SPORT_CFB:
        ranks = ranks or {}
        home_rank = ranks.get(home.team_id) if home else None
        away_rank = ranks.get(away.team_id) if away else None
        if home_rank or away_rank:
            payload["poll_note"] = (
                f"{_rank_phrase(payload['home_name'], home_rank)}, "
                f"{_rank_phrase(payload['away_name'], away_rank)} "
                "(AP poll entering the week)"
            )
        if row.get("is_divisional") and home is not None and home.conference:
            payload["conference_note"] = f"Same-conference clash in the {home.conference}"
    return payload


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
        if target.empty:
            print(f"no {sport} games found for {args.season} week {week}")
            return

        teams_by_abbr = {t.abbr: t for t in db.scalars(select(Team).where(Team.sport == sport))}
        ranks = poll_ranks_entering(db, sport, args.season, week)
        print(f"predicting {len(target)} {sport} games for {args.season} week {week}")

        for _, row in target.iterrows():
            x = row[feature_columns].to_frame().T.astype(float)
            raw = model.predict_proba(x)[:, 1]
            prob = float(calibrator.transform(raw)[0])
            factors = top_factors(explainer, x, prob, sport=sport)

            narrative = narrate(
                build_narration_payload(row, prob, factors, teams_by_abbr, sport, ranks)
            )

            upsert_prediction(db, row["game_id"], version, prob, factors, narrative)
            print(
                f"  {row['game_id']}: home {prob:.1%}"
                + (" (narrated)" if narrative else " (no narrative)")
            )

    print("prediction batch complete")


if __name__ == "__main__":
    main()
