# Blitzcast Backend

Python/FastAPI service that owns the data pipeline, the win-probability
model, and the prediction API. Built by Paymon Software.

## Setup

Requires Python 3.13 and Docker Desktop (for Postgres).

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env   # then paste real API keys into .env
```

Start Postgres (from the repo root):

```powershell
docker compose -f docker/docker-compose.yml up -d
```

All commands below run from `backend/` with the venv's Python
(`.venv\Scripts\python` on Windows, `.venv/bin/python` elsewhere).

## Environment variables (`backend/.env`)

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (default matches docker-compose) |
| `ODDS_API_KEY` | The Odds API (odds refresh) |
| `VISUAL_CROSSING_API_KEY` | Visual Crossing weather (weather refresh) |
| `ANTHROPIC_API_KEY` | Claude API (prediction narration) |
| `ANTHROPIC_MODEL` | Narration model (default `claude-haiku-4-5-20251001`) |
| `CORS_ORIGINS` | Allowed frontend origins (default `http://localhost:3000`) |
| `BLITZCAST_MOCK` | `1` serves fixture predictions (no DB/model needed) |
| `MODEL_VERSION` | Version stamped on artifacts and prediction rows |

Every job degrades gracefully when its key is missing: odds/weather/injury
refreshes print a message and exit; narration writes `null` and continues.

## Commands

| Task | Command |
|---|---|
| Apply migrations | `python -m alembic upgrade head` |
| New migration | `python -m alembic revision --autogenerate -m "msg"` |
| Seed teams/stadiums | `python -m data_pipeline.seed` |
| Historical backfill (2021-2026) | `python -m data_pipeline.backfill` |
| Sync 2026 schedule | `python -m data_pipeline.refresh_schedule` |
| Refresh odds | `python -m data_pipeline.refresh_odds` |
| Refresh weather | `python -m data_pipeline.refresh_weather` |
| Refresh injuries | `python -m data_pipeline.refresh_injuries` |
| Full weekly refresh + predict | `python -m data_pipeline.refresh_week` |
| Persist Elo snapshots | `python -m ml.compute_ratings` |
| Train model | `python -m ml.train` |
| Backtest (writes `ml/reports/`) | `python -m ml.backtest` |
| Predict a week | `python -m app.jobs.predict_week --season 2026 --week 1` |
| Run API | `python -m uvicorn app.main:app --reload` |
| Tests | `python -m pytest` |
| Lint | `python -m ruff check .` |

First-time bootstrap order: migrate → seed → backfill → train → backtest →
predict_week → run API.

## API

- `GET /health`
- `GET /api/teams`
- `GET /api/schedule?season=2026`
- `GET /api/games?week=1&season=2026`
- `GET /api/predictions/{game_id}` (404 unknown game; `prediction_status:
  "pending"` when a game exists but has no prediction yet)

Interactive docs at `http://localhost:8000/docs`. Set `BLITZCAST_MOCK=1` to
serve fixture data so the frontend can develop without a database.

## Data sources & free-tier discipline

- **nflverse** (via `nflreadpy`): schedules incl. 2026, play-by-play EPA,
  injuries, historical closing lines. No key needed. Historical
  `spread_line`/moneylines from nflverse are the *training* market feature.
- **The Odds API** (`ODDS_API_KEY`): current 2026 odds only. Free tier is
  500 requests/month; one call returns all games, so run
  `refresh_odds` **at most once per day** (~30 calls/month). Never call it
  per user request — the app always reads cached odds from Postgres.
- **Visual Crossing** (`VISUAL_CROSSING_API_KEY`): kickoff forecasts for
  upcoming outdoor games; domes and international games are skipped.
- **Claude API** (`ANTHROPIC_API_KEY`): narrates the model output only —
  never computes the prediction.

## Model

XGBoost (shallow, regularized) + Platt calibration on a time-aware holdout.
Features are leakage-safe home-minus-away diffs (Elo, rolling EPA/form,
rest, injuries incl. QB status, weather, market). Walk-forward backtest
results live in [`ml/reports/backtest.md`](ml/reports/backtest.md).
Artifacts in `ml/artifacts/` are gitignored; retrain with `python -m
ml.train`.
