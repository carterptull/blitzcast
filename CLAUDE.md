# Blitzcast

An AI/ML-powered NFL matchup predictor by Paymon Software: pick a 2026
matchup, get a win probability plus a natural-language explanation. See
[DECISIONS.md](./DECISIONS.md) for the rationale behind key technical
choices.

## Architecture

- **`frontend/`** — Next.js 16 + TypeScript + Tailwind v4 (App Router,
  `src/`). Routes: `/` (redirects to `/nfl`), `/[sport]` (week slate for
  `nfl`/`cfb`), `/[sport]/matchup/[gameId]`, `/how-it-works`. Typed API
  client in `src/lib/api.ts`; contract types in `src/lib/types.ts`; mock
  fixtures in `src/lib/mock.ts` and `src/lib/mockCfb.ts`
  (`NEXT_PUBLIC_USE_MOCK=1`).
- **`backend/app/`** — FastAPI. Contract endpoints: `/api/teams`,
  `/api/schedule`, `/api/games`, `/api/predictions/{game_id}`. Predictions
  are **cached rows** written by `app/jobs/predict_week.py` — never computed
  per-request. Narration in `app/services/narrate.py` (Claude, guardrailed).
- **`backend/ml/`** — Elo (`elo.py`), leakage-safe features
  (`features.py`), XGBoost + Platt calibration (`train.py`), walk-forward
  backtest vs Vegas (`backtest.py`), SHAP (`explain.py`). `ml/artifacts/` is
  gitignored except `latest.json` and the current model per sport
  (`model_1.0.0.joblib`, `cfb/model_cfb-1.0.0.joblib`), committed on purpose
  (see DECISIONS.md).
- **`backend/data_pipeline/`** — idempotent upsert loaders: seeds,
  historical backfill (nflverse via `nflreadpy`), weekly refreshes (odds,
  weather, injuries), `refresh_week.py` orchestrator. All external team
  names route through `team_names.py`.
- **Postgres 16** via `docker/docker-compose.yml`; schema managed by
  Alembic (`backend/alembic/`).
- **`diagrams/`** — hand-maintained Mermaid architecture diagrams (start at
  `diagrams/overview.md`). When a change alters something one of them shows
  (schema, a pipeline step or cron schedule, a narration guardrail, the
  prediction read path, ML training windows, security headers), update that
  diagram and its footer stamp in the same PR. The re-check table and
  GitHub Mermaid syntax rules are in `diagrams/README.md`.

## Commands

Backend (from `backend/`, using `.venv\Scripts\python`):
- API: `python -m uvicorn app.main:app --reload` (port 8000)
- Tests: `python -m pytest` · Lint: `python -m ruff check .`
- Migrations: `python -m alembic upgrade head`
- Pipeline: `python -m data_pipeline.seed` / `.backfill` /
  `.refresh_week`; model: `python -m ml.train` / `ml.backtest`;
  predictions: `python -m app.jobs.predict_week`

Frontend (from `frontend/`): `npm run dev` / `lint` / `build` (port 3000)

Full setup + env vars: [README.md](./README.md) and
[backend/README.md](./backend/README.md).

## Conventions & constraints

- **Branding:** public-facing identity is "Paymon" / "Paymon Software"
  only. Never put the maintainer's real name in code, comments, or docs.
  The one functional exception is the portfolio origin inside
  `frontend/next.config.ts`'s `frame-ancestors` CSP value, which has to name
  the embedding domain; everywhere else, call it "the maintainer's
  portfolio site".
- **User-visible copy:** no em dashes or en dashes anywhere a visitor can
  see (UI text, narration, `security.txt`). Check both the literal
  characters and the `&mdash;`/`&ndash;` entities: a past bug shipped
  through the entity form after a literal-character grep missed it.
- **Version:** SemVer, single source of truth is `frontend/package.json`'s
  `version` field (displayed in the footer); releases are tagged on GitHub.
  `MODEL_VERSION` (`1.0.0`; `MODEL_VERSION_CFB` `cfb-1.0.0`) is separate —
  it stamps ML artifacts and prediction rows, not the app release.
  `security.txt`'s `Expires` date needs renewing before 2027-09-14.
- **Leakage rule (ML):** every feature for game G uses only data from
  strictly before G's kickoff. Tests enforce this — keep it that way.
- **Completion invariant:** never key "is this game over" off the
  `Game.status` column. It's derived, unindexed, and has been wrong before
  (set final on the home score alone). Always check
  `home_score is not None and away_score is not None` directly, at every
  call site (status filter, verdict grading, the season record).
- **LLM boundary:** Claude narrates model output only; it never predicts,
  never alters probabilities. Guardrails live in `narrate.py` — they check
  both percentage magnitude (`_percentages_consistent`) and team
  attribution (`_favorite_attribution_consistent`); a checkable fact
  (which team is actually favored) must never be misstated even if the
  cited number is correct.
- **Market-factor SHAP direction:** in `ml/explain.py`, `market_spread_home`
  and `market_home_prob`'s displayed `direction` comes from the feature's
  own raw value, never the SHAP sign — these represent an independently
  checkable fact (which team the market favors), and a tree ensemble's
  local SHAP attribution can legitimately point the other way near a
  toss-up line. Every other feature still uses SHAP sign; only add a
  feature to `_MARKET_GROUND_TRUTH` if it has a similar independent truth
  to check against.
- **Neutral-site games:** `Game.venue_name`/`is_neutral_site` hold the raw
  nflverse venue for games with no Team-derived stadium (`stadium_id`
  NULL). `refresh_weather.py` fetches these by venue-name geocoding
  instead of lat/lon; don't reintroduce a bare `stadium is None: skip`
  check without also checking `venue_name`.
- **API keys** live in gitignored `.env` files (examples checked in). All
  jobs degrade gracefully when keys are missing — preserve that property.
- **Odds API budget:** free tier, 500 req/month — odds are fetched by the
  daily/weekly batch only, never per user request.
- **Comments:** minimal, clean, simple.
- Python: SQLAlchemy 2.x typed `Mapped` style, ruff-clean. Schema changes
  go through Alembic migrations, never manual edits.
- **Python dependencies are pinned** (`==`) in `backend/requirements.txt`
  and `requirements-dev.txt`. The committed `.joblib` models were saved
  under the pinned xgboost/scikit-learn, so bump those only together with a
  retrain and a re-commit of the artifacts.
- **Adding an API field:** this repo has shipped three separate
  contract-drift bugs from `frontend/src/lib/types.ts` disagreeing with
  `backend/app/schemas.py` on nullability or enum values. A new field
  touches all five of these, in the same change: `backend/app/schemas.py`;
  the builder in `backend/app/services/predictions.py`; the mock path in
  `backend/app/mock_data.py`; `frontend/src/lib/types.ts` (match
  nullability exactly); and `frontend/src/lib/mock.ts` /
  `frontend/src/lib/mockCfb.ts`. Assert it in
  `frontend/src/lib/__tests__/api.test.ts`.
