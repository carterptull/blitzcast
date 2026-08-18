# Blitzcast

An AI/ML-powered NFL matchup predictor by Paymon Software: pick a 2026
matchup, get a win probability plus a natural-language explanation. See
[DECISIONS.md](./DECISIONS.md) for the rationale behind key technical
choices.

## Architecture

- **`frontend/`** — Next.js 16 + TypeScript + Tailwind v4 (App Router,
  `src/`). Routes: `/` (week slate) and `/matchup/[gameId]`. Typed API
  client in `src/lib/api.ts`; contract types in `src/lib/types.ts`; mock
  fixtures in `src/lib/mock.ts` (`NEXT_PUBLIC_USE_MOCK=1`).
- **`backend/app/`** — FastAPI. Contract endpoints: `/api/teams`,
  `/api/schedule`, `/api/games`, `/api/predictions/{game_id}`. Predictions
  are **cached rows** written by `app/jobs/predict_week.py` — never computed
  per-request. Narration in `app/services/narrate.py` (Claude, guardrailed).
- **`backend/ml/`** — Elo (`elo.py`), leakage-safe features
  (`features.py`), XGBoost + Platt calibration (`train.py`), walk-forward
  backtest vs Vegas (`backtest.py`), SHAP (`explain.py`). Artifact bundle in
  `ml/artifacts/` (gitignored) + `latest.json` (committed).
- **`backend/data_pipeline/`** — idempotent upsert loaders: seeds,
  historical backfill (nflverse via `nflreadpy`), weekly refreshes (odds,
  weather, injuries), `refresh_week.py` orchestrator. All external team
  names route through `team_names.py`.
- **Postgres 16** via `docker/docker-compose.yml`; schema managed by
  Alembic (`backend/alembic/`).

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
- **Version:** SemVer, single source of truth is `frontend/package.json`'s
  `version` field (displayed in the footer); releases are tagged on GitHub.
  `MODEL_VERSION` (0.1.0) is separate — it stamps ML artifacts and
  prediction rows, not the app release.
- **Leakage rule (ML):** every feature for game G uses only data from
  strictly before G's kickoff. Tests enforce this — keep it that way.
- **Completion invariant:** never key "is this game over" off the
  `Game.status` column. It's derived, unindexed, and has been wrong before
  (set final on the home score alone). Always check
  `home_score is not None and away_score is not None` directly, at every
  call site (status filter, verdict grading, the season record).
- **LLM boundary:** Claude narrates model output only; it never predicts,
  never alters probabilities. Guardrails live in `narrate.py`.
- **API keys** live in gitignored `.env` files (examples checked in). All
  jobs degrade gracefully when keys are missing — preserve that property.
- **Odds API budget:** free tier, 500 req/month — odds are fetched by the
  daily/weekly batch only, never per user request.
- **Comments:** minimal, clean, simple.
- Python: SQLAlchemy 2.x typed `Mapped` style, ruff-clean. Schema changes
  go through Alembic migrations, never manual edits.
- **Adding an API field:** this repo has shipped three separate
  contract-drift bugs from `frontend/src/lib/types.ts` disagreeing with
  `backend/app/schemas.py` on nullability or enum values. A new field
  touches all five of these, in the same change: `backend/app/schemas.py`;
  the builder in `backend/app/services/predictions.py`; the mock path in
  `backend/app/mock_data.py`; `frontend/src/lib/types.ts` (match
  nullability exactly); and `frontend/src/lib/mock.ts` /
  `frontend/src/lib/mockCfb.ts`. Assert it in
  `frontend/src/lib/__tests__/api.test.ts`.
