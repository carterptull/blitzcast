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
| `CFBD_API_KEY` | CollegeFootballData API (all CFB seed/backfill/refresh jobs) |
| `VISUAL_CROSSING_API_KEY` | Visual Crossing weather (weather refresh) |
| `ANTHROPIC_API_KEY` | Claude API (prediction narration) |
| `ANTHROPIC_MODEL` | Narration model (default `claude-haiku-4-5-20251001`) |
| `CORS_ORIGINS` | Allowed frontend origins (default `http://localhost:3000`) |
| `BLITZCAST_MOCK` | `1` serves fixture predictions (no DB/model needed) |
| `MODEL_VERSION` | Version stamped on NFL artifacts and prediction rows (default `1.0.0`) |
| `MODEL_VERSION_CFB` | Same stamp for CFB (default `cfb-1.0.0`) |

Every job degrades gracefully when its key is missing: odds/weather/injury
refreshes print a message and exit; narration writes `null` and continues.

## Commands

| Task | Command |
|---|---|
| Apply migrations | `python -m alembic upgrade head` |
| New migration | `python -m alembic revision --autogenerate -m "msg"` |
| Seed teams/stadiums (NFL) | `python -m data_pipeline.seed` |
| Historical backfill (NFL, 2021-2026) | `python -m data_pipeline.backfill` |
| Sync 2026 schedule (NFL) | `python -m data_pipeline.refresh_schedule` |
| Refresh team game stats (NFL) | `python -m data_pipeline.refresh_stats [--season 2026]` |
| Refresh odds (NFL) | `python -m data_pipeline.refresh_odds` |
| Refresh weather (NFL) | `python -m data_pipeline.refresh_weather [--sport nfl\|cfb]` |
| Refresh injuries (NFL) | `python -m data_pipeline.refresh_injuries` |
| Full weekly refresh + predict (NFL) | `python -m data_pipeline.refresh_week` |
| Seed teams/conferences (CFB) | `python -m data_pipeline.seed_cfb` |
| Historical backfill (CFB, 2021-2026) | `python -m data_pipeline.backfill_cfb` |
| Sync current-season schedule (CFB) | `python -m data_pipeline.refresh_schedule_cfb [--season 2026]` |
| Refresh AP/Coaches polls (CFB) | `python -m data_pipeline.refresh_polls_cfb` |
| Full weekly refresh + predict (CFB) | `python -m data_pipeline.refresh_week_cfb` |
| Persist Elo snapshots | `python -m ml.compute_ratings --sport nfl\|cfb` |
| Train model | `python -m ml.train --sport nfl\|cfb` |
| Backtest (writes `ml/reports/`) | `python -m ml.backtest --sport nfl\|cfb` |
| Predict a week | `python -m app.jobs.predict_week --season 2026 --week 1 --sport nfl\|cfb` |
| Backfill walk-forward predictions | `python -m app.jobs.backfill_predictions --sport nfl\|cfb` |
| Run API | `python -m uvicorn app.main:app --reload` |
| Tests | `python -m pytest` |
| Lint | `python -m ruff check .` |

`--sport` defaults to `nfl` on every ML/prediction command, including
`refresh_weather` (a full FBS slate would burn the Visual Crossing free
tier). CFB has no weather or injuries refresh: `refresh_schedule_cfb`,
`refresh_odds --sport cfb`, and `refresh_polls_cfb` are the only in-season
CFB syncs, bundled by `refresh_week_cfb`.

`refresh_stats` re-ingests play-by-play into `team_game_stats`, which feeds
the rolling EPA and turnover form features. It runs inside `refresh_week`
and skips cleanly until the season's first game is final.

`backfill_predictions` reconstructs a season-record's worth of history for
the "Called it"/"Missed" UI and the `/api/record` endpoint: it walk-forward
retrains a model per holdout season (2023-2025) that has never seen that
season, scores it, and writes the result under a distinct
`backtest-1.0.0` / `backtest-cfb-1.0.0` model version, mirroring
`ml/backtest.py`. The shipped model artifact is never used for this,
since it trained on 2023-2025 and its accuracy on them would be in-sample.
Rows written this way are excluded from `/api/record` and from the slate's
prediction probability, and are labeled "Reconstructed from a backtest,
not a live call made before kickoff" on the matchup page. Its own ad-hoc
verification snippet (used during development, not part of the committed
report) does not filter CFB to FBS-vs-FBS the way `ml/backtest.py`'s
report does, so re-running it will read a higher CFB accuracy than the
report's number unless filtered manually.

First-time bootstrap order per sport: migrate (once) → seed → backfill →
compute_ratings → train → backtest → predict_week → run API.
(`compute_ratings` persists Elo snapshots to `team_ratings` for inspection
and analysis; the serving path does not read that table, since
`ml/features.py` replays Elo itself when building features.) NFL and CFB
pipelines are independent. Run either or both in any order after
migrations.

## API

- `GET /health`
- `GET /api/teams`
- `GET /api/schedule?season=2026`
- `GET /api/games?week=1&season=2026`
- `GET /api/predictions/{game_id}` (404 unknown game; `prediction_status:
  "pending"` when a game exists but has no prediction yet)
- `GET /api/record?sport=NFL|CFB&season=2026`: current-season accuracy
  (`correct`/`total`) alongside the market's accuracy over the identical
  graded sample (`market_correct`/`total`). A game is graded only when it
  has a final score, a non-tie result, a model probability that isn't an
  exact 0.5 pick'em, and a market probability that clears the same bar;
  reconstructed (`backtest*`) predictions never count. `sufficient` is
  `false` below 10 graded games. Omitting `sport` combines both.

`/api/teams`, `/api/schedule`, and `/api/games` take an optional
`sport=NFL|CFB` query param (case-insensitive, default `NFL`; unknown values
422). `/api/predictions/{game_id}` needs no sport: game ids are globally
unique (CFB ids are prefixed `cfb_`) and the response carries `sport`.
`predict_week` takes `--sport nfl|cfb` (default `nfl`).

`/api/games` and `/api/schedule` also take `status=all|final|upcoming`
(default `all`), filtering on whether both scores are present, not on the
`Game.status` column. Unlike `sport`, an unrecognized `status` value falls
back to `all` silently rather than 422ing.

Interactive docs at `http://localhost:8000/docs`. Set `BLITZCAST_MOCK=1` to
serve fixture data so the frontend can develop without a database.

## Data sources & free-tier discipline

- **nflverse** (via `nflreadpy`): schedules incl. 2026, play-by-play EPA,
  injuries, historical closing lines. No key needed. Historical
  `spread_line`/moneylines from nflverse are the *training* market feature.
  For a week nflverse hasn't scheduled real broadcast times for yet
  (observed for Week 18 seasons far in advance), it fills every game's
  `gametime` with one repeated placeholder string rather than leaving it
  blank; `games_loader.py` detects that pattern and writes `kickoff_time`
  as `NULL` (shown as TBD) for the whole week instead of a fake confident
  time. CFB already handled this correctly via CFBD's explicit TBD flag.
- **The Odds API** (`ODDS_API_KEY`): current 2026 odds only. Free tier is
  500 requests/month; one call returns all games, so run
  `refresh_odds` **at most once per day** (~30 calls/month). Never call it
  per user request. The app always reads cached odds from Postgres.
- **CollegeFootballData** (`CFBD_API_KEY`): the single source for CFB.
  Teams, venues, games, betting lines, team-game PPA, and AP/Coaches
  polls. Every CFB job exits early when the key is missing.
- **Visual Crossing** (`VISUAL_CROSSING_API_KEY`): kickoff forecasts for
  upcoming outdoor games; domes and international games are skipped.
- **Claude API** (`ANTHROPIC_API_KEY`): narrates the model output only,
  never computes the prediction.

## Model

XGBoost (shallow, regularized) + Platt calibration on a time-aware holdout.
Features are leakage-safe home-minus-away diffs (Elo, rolling EPA/form,
rest, injuries incl. QB status, weather, market). Walk-forward backtest
results live in [`ml/reports/backtest.md`](ml/reports/backtest.md).
Artifacts in `ml/artifacts/` are gitignored; retrain with `python -m
ml.train`.

`ml/train.py` asserts the training and calibration windows are temporally
disjoint (`assert_temporally_disjoint`, raises if the latest training
kickoff is not strictly before the earliest calibration kickoff) before
fitting. There's no plan to retrain mid-season today: Elo and the rolling
form features already adapt within a season without a retrain, and
widening `TRAIN_SEASONS` mid-season would need its own validated
methodology first. The guard exists so that whenever that happens, a
window overlap fails loudly instead of quietly leaking into the model.
