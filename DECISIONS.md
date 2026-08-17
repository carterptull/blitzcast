# DECISIONS.md

Concise log of significant technical decisions: what / why / alternative considered.
Kept for the owner's reference (interview prep, future maintenance).

## Walk-forward backtesting instead of random k-fold

Model is validated season-by-season, expanding-window (train on seasons up to N, predict
season N+1, roll forward), never randomly shuffled cross-validation. **Why:** random k-fold
leaks future games into training when the target is inherently time-ordered. A model that's
never seen 2025 results has no business being validated on a random split that includes them.
**Alternative:** standard k-fold CV: faster to run, but the resulting metrics would be
meaningless for a system meant to predict future games from past ones; rejected.

## Difference features over raw absolute features

Model inputs are mostly home-minus-away deltas (`elo_diff`, `epa_off_diff`, `rest_diff`) rather
than separate home/away columns. **Why:** smaller, more stable model on a limited dataset
(~1,080 training games), and a cleaner SHAP story: "+0.14 from home Elo edge" reads better
than four separate absolute-value contributions that the reader has to mentally subtract.
**Alternative:** keep home and away features separate and let the tree model learn the
interaction: plausible with more data, but adds variance without a matching sample size.

## Calibration treated as a first-class metric, not an afterthought

Model probabilities are calibrated (Platt/isotonic) against a time-aware holdout, the most
recent season, not a random subset. **Why:** tree-based classifiers are frequently
overconfident; without calibration a "70%" prediction might really only win 55% of the time,
which defeats the purpose of reporting a probability at all. **Alternative:** report raw model
output uncalibrated: simpler, but the number would be decorative rather than meaningful;
rejected.

## Vegas closing line as the validation baseline, not just an accuracy target

Every backtest reports the model's Brier score and log-loss next to the same metrics computed
from the market's closing-line implied probabilities. **Why:** "63% accurate" means very little
on its own. Comparing against the market (one of the hardest baselines to beat, using only
public data) is the actual evidence the model is doing something real, and an honest result
either way is worth reporting. **Alternative:** report accuracy/AUC only: easier to make look
good, but doesn't tell a reader anything about whether the model is actually well-calibrated or
competitive; rejected.

## Batch-generated predictions, not per-request inference

Predictions are computed on a schedule (after each weekly data refresh) and written to Postgres;
the API only ever reads cached rows, never runs the model live on a request. **Why:** several
upstream data sources (odds, weather) are rate-limited free tiers, and per-request inference
would make API usage unpredictable and the app slower for no real benefit, since odds/injuries
don't change minute-to-minute. **Alternative:** run inference on each API call: simpler
mentally, but ties app latency and external API budget to traffic; rejected.

## Anti-leakage as an explicit, tested property of feature engineering

Every rolling feature (Elo, EPA/play, form) is computed strictly as-of the week before the
target game: nothing derived from data at or after kickoff. This is enforced with a dedicated
test, not just a coding convention. **Why:** leakage is the most common way a "surprisingly
good" backtest turns out to be fake; a model that accidentally sees the outcome it's predicting
will look great in testing and useless in production. **Alternative:** trust careful coding
without a leakage-specific test: too easy to silently regress when the pipeline changes;
rejected.

## SHAP for explainability instead of a black-box probability only

Each prediction ships with the top contributing features (signed, human-labeled) via SHAP
TreeExplainer, not just a bare percentage. **Why:** a probability without reasoning is much less
useful and much less trustworthy: showing which factors moved the needle (and in which
direction) makes the model's behavior auditable and the output far more interesting to read.
**Alternative:** ship the probability alone and skip explainability: simpler to build, but
turns the model into a black box with no way to sanity-check individual predictions; rejected.

## LLM narration layer strictly downstream of the model, never upstream

The narration step receives the model's probability and SHAP factors as fixed inputs and only
turns them into prose: it cannot change the numbers, and a failed narration falls back to
showing the factor list without prose rather than blocking the prediction. **Why:** keeping the
actual prediction deterministic and testable was the whole point of using a real ML model in the
first place; letting a language model touch the math would undermine the backtest results
entirely. **Alternative:** let the LLM generate both the number and the explanation together:
faster to prototype, but non-deterministic and impossible to validate rigorously; rejected.

## CFB added as a `sport` discriminator, not a fork

College football shares one Postgres DB and one FastAPI app with NFL: `sport=NFL|CFB` is a
query param on the schedule/games/teams endpoints and a `--sport` flag on the ML CLI commands
(`compute_ratings`, `train`, `backtest`, `predict_week`), rather than a second copy of the
codebase. Each sport still gets its own Elo history, trained model, and calibration
(`ml/reports/backtest_cfb.md`, `ml/artifacts/cfb/`), since NFL and CFB have genuinely different
score distributions and shouldn't share one model. **Why:** the app-layer code (API contract,
prediction batch shape, frontend components) is sport-agnostic and would otherwise be duplicated
wholesale for one extra query param's worth of difference; only the parts that are *actually*
sport-specific (data sources, model artifacts, injury-data availability) diverge.
**Alternative:** a separate `cfb-blitzcast` app/repo: clean isolation, but doubles the
maintenance surface for routing, schemas, and frontend chrome that don't differ by sport;
rejected.

## Haiku 4.5 as the default narration model, Sonnet as an override

`ANTHROPIC_MODEL` defaults to `claude-haiku-4-5-20251001` (`backend/app/config.py`), not a
larger model, and is a setting rather than a literal scattered through `narrate.py`. **Why:**
narration output is short (2–4 sentences) and high-volume-ish (~16 NFL + ~65 CFB games/week);
Haiku's latency and cost are negligible at that volume and the task (restating given numbers in
an energetic voice) doesn't need a frontier model's reasoning. **Alternative:** hardcode Sonnet
for consistently higher prose quality: plausible if narration quality ever becomes the
bottleneck, which is exactly why it's a config override, not a rewrite, away.

## Odds API: one batch call per day, never per request

The Odds API's free tier (500 requests/month) is called once daily by the scheduled refresh job,
which returns all of that week's games in a single response, never invoked on a user request.
**Why:** at 30 calls/month this leaves comfortable headroom under the free-tier cap regardless of
site traffic, and odds don't move meaningfully minute-to-minute, so there's no UX cost to reading
a cached row instead of a live call. **Alternative:** fetch fresh odds per matchup-detail page
view: simple to reason about, but ties API budget directly to traffic and would blow through
500 requests/month almost immediately; rejected.

## Frontend and backend as separate services, not a monolith

Next.js (`frontend/`) and FastAPI (`backend/`) are two processes communicating over an internal
HTTP API, not a single full-stack framework serving both. **Why:** the ML/data pipeline is a
Python-native problem (XGBoost, SHAP, nflverse/CFBD tooling) with no good equivalent in the
Node ecosystem, and a typed API contract (`src/lib/types.ts` mirroring the FastAPI schemas) keeps
the frontend swappable or independently deployable later. **Alternative:** a Python-rendered
frontend (e.g. Jinja/HTMX): would avoid the contract-sync overhead, but trades away Next.js's
component/theming ergonomics for a UI that's meant to look polished and be mobile-friendly;
rejected.
