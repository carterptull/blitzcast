# ML pipeline: train, validate, serve

Three separate paths share one feature builder. Training produces the committed artifact,
validation measures it honestly against the betting market, and serving applies it daily. Each
sport (NFL, CFB) runs the same shape with its own Elo configuration, model, and calibration.

```mermaid
flowchart LR
    hist[("Postgres history<br/><small>games · team_game_stats · odds<br/>weather · injuries · poll_ranks</small>")]

    features["build_features()<br/><small>ml/features.py<br/>Elo replayed game by game<br/>rolling EPA and form as of each kickoff<br/>rest, injuries, weather, market<br/>mostly home-minus-away differences</small>"]

    subgraph train["Train: python -m ml.train"]
        split["Train seasons 2022, 2023, 2024<br/>Calibration season 2025"]
        disjoint{"assert_temporally_disjoint<br/><small>last training kickoff strictly<br/>before first calibration kickoff?</small>"}
        leak(["Raise and stop"])
        fit["XGBoost classifier<br/><small>shallow, regularized</small>"]
        platt["PlattCalibrator<br/><small>fit on 2025 only</small>"]
        artifact[["model_1.0.0.joblib, cfb/model_cfb-1.0.0.joblib<br/>and latest.json<br/><small>committed to git</small>"]]
    end

    subgraph validate["Validate: walk-forward, never random k-fold"]
        bt["ml/backtest.py<br/><small>for each holdout season 2023, 2024, 2025<br/>train only on earlier seasons</small>"]
        vegas["Brier score and accuracy<br/>vs de-vigged closing lines<br/><small>ml/reports/backtest.md, backtest_cfb.md</small>"]
        backfill["app/jobs/backfill_predictions.py<br/><small>same walk-forward method</small>"]
        btrows[("predictions rows<br/><small>backtest-1.0.0, backtest-cfb-1.0.0<br/>excluded from the slate and /api/record</small>")]
    end

    subgraph serve["Serve: daily, app/jobs/predict_week.py"]
        load["load_latest(sport)"]
        proba["predict_proba, then calibrator.transform"]
        shap["SHAP TreeExplainer<br/><small>top_factors, n=4</small>"]
        live[("predictions rows<br/><small>1.0.0, cfb-1.0.0</small>")]
    end

    hist --> features
    features --> split --> disjoint
    disjoint -->|no| leak
    disjoint -->|yes| fit --> platt --> artifact
    features --> bt --> vegas
    bt -.->|"same method"| backfill --> btrows
    artifact --> load --> proba --> shap --> live
    features --> proba

    style train fill:transparent,stroke:#1565C0,stroke-width:2px
    style validate fill:transparent,stroke:#6A1B9A,stroke-width:2px
    style serve fill:transparent,stroke:#2E7D32,stroke-width:2px
```

**The leakage rule is a tested property, not a convention.** Every feature for a game is computed
only from data strictly before that game's kickoff, and a dedicated test enforces it.
`assert_temporally_disjoint` adds a second guard at training time, so that if the training window
is ever widened, an overlap with the calibration season fails loudly instead of leaking. See
"Anti-leakage as an explicit, tested property" and "No mid-season retrain" in
[`DECISIONS.md`](../DECISIONS.md).

**Validation compares against the market, not just a hit rate.** A bare accuracy number says
little; the backtest reports Brier score and accuracy next to the de-vigged closing line over the
same games, and the model lands close to the line without beating it. The README's backtest
tables come from here.

**Backfilled history is labeled so it can't flatter the model.** The shipped model trained on
2023-2025, so scoring it on those seasons would be in-sample. `backfill_predictions` instead
reuses the walk-forward models and writes them under `backtest-*` versions that the live record
ignores. See "Backfilled predictions from walk-forward retraining, not the shipped model".

**Calibration is first-class:** tree ensembles tend to be overconfident, so raw scores are Platt
calibrated on a held-out, most-recent season before a "70%" is ever shown to anyone.

---
_Last updated: 2026-09-14 · reflects v1.0.10_
