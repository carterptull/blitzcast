"""Walk-forward backtest by season, with a market-baseline comparison and a
calibration (reliability) plot.

For each holdout season S: train on all seasons before S (the last of those
doubles as the early-stopping/calibration split), predict S out-of-sample.

CFB: the model trains on FBS-vs-FBS + FBS-vs-FCS rows, but the calibrator
fit, the market baseline, and the headline metrics are FBS-vs-FBS only
(FBS-vs-FCS outcomes are near-deterministic and inflate apparent skill).

Usage: python -m ml.backtest [--sport nfl|cfb]
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL
from ml.features import training_frame
from ml.train import fbs_vs_fbs, fit_model, predict_calibrated

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

FIRST_SEASON = 2022
HOLDOUT_SEASONS = [2023, 2024, 2025]

SPORT_BACKTEST = {
    SPORT_NFL: {
        "first_season": FIRST_SEASON,
        "holdout_seasons": HOLDOUT_SEASONS,
        # Single-history-season fallback split (NFL: week 12 of 18).
        "week_split": 12,
        "report": "backtest.md",
        "plot": "calibration.png",
        "title": "# Backtest — walk-forward by season",
        "baseline_note": [
            "Model trains only on seasons before each holdout season; the market",
            "baseline uses de-vigged closing moneyline probabilities (nflverse).",
        ],
    },
    SPORT_CFB: {
        # 2021-2025 backfill window: 2021 seeds rolling form, 2022 is the
        # first trainable season, 2023-2025 are the holdouts.
        "first_season": 2022,
        "holdout_seasons": [2023, 2024, 2025],
        # Mid-season split of a ~15-week CFB regular season.
        "week_split": 8,
        "report": "backtest_cfb.md",
        "plot": "calibration_cfb.png",
        "title": "# CFB Backtest — walk-forward by season",
        "baseline_note": [
            "Model trains only on seasons before each holdout season; the market",
            "baseline uses de-vigged CFBD closing lines. The model trains on",
            "FBS-vs-FBS and FBS-vs-FCS games, but the calibrator and all metrics",
            "below are FBS-vs-FBS only: mismatch outcomes are near-deterministic",
            "and would inflate apparent reliability in the competitive range.",
        ],
    },
}


def season_metrics(y: np.ndarray, probs: np.ndarray) -> dict:
    return {
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs)),
        "accuracy": float(((probs > 0.5) == y).mean()),
        "auc": float(roc_auc_score(y, probs)),
    }


def calibration_plot(y: np.ndarray, probs: np.ndarray, path: Path) -> None:
    bins = np.linspace(0.0, 1.0, 11)
    idx = np.digitize(probs, bins[1:-1])
    pred_mean, actual_rate = [], []
    for b in range(10):
        mask = idx == b
        if mask.sum() >= 5:
            pred_mean.append(probs[mask].mean())
            actual_rate.append(y[mask].mean())

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="#9aa5a1", label="Perfect calibration")
    ax.plot(pred_mean, actual_rate, marker="o", color="#1b4332", label="Model")
    ax.set_xlabel("Predicted home win probability")
    ax.set_ylabel("Actual home win rate")
    ax.set_title("Reliability curve — out-of-sample seasons")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL
    cfg = SPORT_BACKTEST[sport]
    holdout_seasons = cfg["holdout_seasons"]
    is_cfb = sport == SPORT_CFB

    with session_scope() as db:
        df = training_frame(
            db, list(range(cfg["first_season"], holdout_seasons[-1] + 1)), sport=sport
        )

    rows = []
    pooled_y, pooled_model, pooled_vegas = [], [], []
    for season in holdout_seasons:
        history = df[df["season"] < season]
        holdout = df[df["season"] == season]
        calib_season = int(history["season"].max())
        train_df = history[history["season"] < calib_season]
        calib_df = history[history["season"] == calib_season]
        if train_df.empty:
            # Single history season: split it by week instead.
            train_df = history[history["week"] <= cfg["week_split"]]
            calib_df = history[history["week"] > cfg["week_split"]]

        calib_fit_df = calib_df[fbs_vs_fbs(calib_df)] if is_cfb else None
        model, calibrator = fit_model(train_df, calib_df, calib_fit_df)

        eval_df = holdout[fbs_vs_fbs(holdout)] if is_cfb else holdout
        probs = predict_calibrated(model, calibrator, eval_df)
        y = eval_df["home_win"].astype(int).to_numpy()

        market = eval_df["market_home_prob"].to_numpy(dtype=float)
        has_market = ~np.isnan(market)

        m = season_metrics(y, probs)
        v = season_metrics(y[has_market], market[has_market])
        rows.append({"season": season, "n_games": len(y), "model": m, "vegas": v})
        pooled_y.append(y)
        pooled_model.append(probs)
        pooled_vegas.append(np.where(has_market, market, np.nan))
        print(
            f"{season}: model brier {m['brier']:.4f} vs vegas {v['brier']:.4f}, "
            f"acc {m['accuracy']:.3f} vs {v['accuracy']:.3f}"
        )

    y_all = np.concatenate(pooled_y)
    p_all = np.concatenate(pooled_model)
    v_all = np.concatenate(pooled_vegas)
    has_v = ~np.isnan(v_all)
    overall_model = season_metrics(y_all, p_all)
    overall_vegas = season_metrics(y_all[has_v], v_all[has_v])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_path = REPORTS_DIR / cfg["plot"]
    calibration_plot(y_all, p_all, plot_path)

    lines = [
        cfg["title"],
        "",
        *cfg["baseline_note"],
        "",
        "| Season | Games | Model Brier | Vegas Brier | Model LogLoss | Vegas LogLoss "
        "| Model Acc | Vegas Acc | Model AUC | Vegas AUC |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        m, v = r["model"], r["vegas"]
        lines.append(
            f"| {r['season']} | {r['n_games']} | {m['brier']:.4f} | {v['brier']:.4f} "
            f"| {m['log_loss']:.4f} | {v['log_loss']:.4f} | {m['accuracy']:.3f} "
            f"| {v['accuracy']:.3f} | {m['auc']:.3f} | {v['auc']:.3f} |"
        )
    m, v = overall_model, overall_vegas
    lines += [
        f"| **All** | {len(y_all)} | **{m['brier']:.4f}** | **{v['brier']:.4f}** "
        f"| {m['log_loss']:.4f} | {v['log_loss']:.4f} | {m['accuracy']:.3f} "
        f"| {v['accuracy']:.3f} | {m['auc']:.3f} | {v['auc']:.3f} |",
        "",
        f"![Calibration](./{cfg['plot']})",
        "",
    ]
    report_path = REPORTS_DIR / cfg["report"]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {report_path} and {plot_path}")
    print("overall:", {"model": overall_model, "vegas": overall_vegas})


if __name__ == "__main__":
    main()
