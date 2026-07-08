"""Walk-forward backtest by season, with a Vegas-baseline comparison and a
calibration (reliability) plot.

For each holdout season S: train on all seasons before S (the last of those
doubles as the early-stopping/calibration split), predict S out-of-sample.

Usage: python -m ml.backtest
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from app.db import session_scope
from ml.features import training_frame
from ml.train import fit_model, predict_calibrated

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

FIRST_SEASON = 2022
HOLDOUT_SEASONS = [2023, 2024, 2025]


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
    with session_scope() as db:
        df = training_frame(db, list(range(FIRST_SEASON, HOLDOUT_SEASONS[-1] + 1)))

    rows = []
    pooled_y, pooled_model, pooled_vegas = [], [], []
    for season in HOLDOUT_SEASONS:
        history = df[df["season"] < season]
        holdout = df[df["season"] == season]
        calib_season = int(history["season"].max())
        train_df = history[history["season"] < calib_season]
        calib_df = history[history["season"] == calib_season]
        if train_df.empty:
            # Single history season: split it by week instead.
            train_df = history[history["week"] <= 12]
            calib_df = history[history["week"] > 12]

        model, calibrator = fit_model(train_df, calib_df)
        probs = predict_calibrated(model, calibrator, holdout)
        y = holdout["home_win"].astype(int).to_numpy()

        market = holdout["market_home_prob"].to_numpy(dtype=float)
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
    plot_path = REPORTS_DIR / "calibration.png"
    calibration_plot(y_all, p_all, plot_path)

    lines = [
        "# Backtest — walk-forward by season",
        "",
        "Model trains only on seasons before each holdout season; the market",
        "baseline uses de-vigged closing moneyline probabilities (nflverse).",
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
        "![Calibration](./calibration.png)",
        "",
    ]
    report_path = REPORTS_DIR / "backtest.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {report_path} and {plot_path}")
    print("overall:", {"model": overall_model, "vegas": overall_vegas})


if __name__ == "__main__":
    main()
