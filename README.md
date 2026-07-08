# Blitzcast

An AI/ML-powered NFL matchup predictor by **Paymon Software**. Pick a 2026
matchup, get a win probability (0–100%) plus a broadcaster-style explanation
of the key factors behind it — built on a trained, calibrated XGBoost model
with SHAP explainability. Claude narrates the model's output; it never makes
the prediction.

**Version: 0.1.0-beta** (local-only; see [VERSION](./VERSION))

Scope, ML approach, and roadmap: [PLANNING.md](./PLANNING.md) ·
Build spec: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) ·
Backend commands: [backend/README.md](./backend/README.md)

## How it works

1. **Data pipeline** (`backend/data_pipeline/`) pulls schedules, results,
   play-by-play EPA, injuries, odds, and weather into Postgres — nflverse
   (via `nflreadpy`) for history, The Odds API + Visual Crossing + ESPN for
   the current week.
2. **Model** (`backend/ml/`) — XGBoost home-win classifier over 20
   leakage-safe features (Elo, rolling EPA/form, rest, injuries, weather,
   market), Platt-calibrated, walk-forward backtested against the Vegas
   closing line.
3. **API** (`backend/app/`) — FastAPI serves cached predictions; a weekly
   batch job (features → predict → SHAP → narrate → upsert) does the work.
4. **Narration** — Claude (Haiku 4.5) turns the probability + top SHAP
   factors into 2–4 sentences of radio-broadcaster color. Guardrailed: it
   can never change or invent the numbers.
5. **Frontend** (`frontend/`) — Next.js + Tailwind: week slate, turf-hero
   matchup pages, light/dark themes, mobile-first.

## Backtest results

Walk-forward by season (train strictly on prior seasons), compared to
de-vigged closing moneylines:

| Season | Games | Model Brier | Vegas Brier | Model Acc | Vegas Acc |
|---|---|---|---|---|---|
| 2023 | 285 | 0.2405 | 0.2186 | 0.604 | 0.677 |
| 2024 | 285 | 0.2100 | 0.2010 | 0.702 | 0.705 |
| 2025 | 285 | 0.2191 | 0.2104 | 0.663 | 0.663 |
| **All** | 855 | **0.2232** | **0.2100** | 0.656 | 0.682 |

The model approaches closing-line accuracy using only public data (and
matches Vegas accuracy in 2025). Full report + calibration plot:
`backend/ml/reports/`.

## Quick start (local)

Requires Node 22+, Python 3.13, Docker Desktop.

```powershell
# 1. Database
docker compose -f docker/docker-compose.yml up -d

# 2. Backend — see backend/README.md for full pipeline commands
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env            # paste real API keys
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m data_pipeline.seed
.venv\Scripts\python -m data_pipeline.backfill
.venv\Scripts\python -m ml.train
.venv\Scripts\python -m app.jobs.predict_week
.venv\Scripts\python -m uvicorn app.main:app --reload   # http://localhost:8000

# 3. Frontend (new terminal)
cd frontend
npm install
copy .env.example .env.local      # set NEXT_PUBLIC_BUYMEACOFFEE_URL etc.
npm run dev                        # http://localhost:3000
```

In-season weekly refresh (odds → weather → injuries → predictions):

```powershell
.venv\Scripts\python -m data_pipeline.refresh_week
```

**No API keys yet?** Everything still runs: refresh jobs skip politely,
narration falls back to the factor list, and the frontend has a full mock
mode (`NEXT_PUBLIC_USE_MOCK=1`) plus the backend's `BLITZCAST_MOCK=1`.

## Repo structure

```
blitzcast/
├── frontend/            Next.js 16 + TypeScript + Tailwind v4 (App Router)
├── backend/
│   ├── app/             FastAPI: routers, schemas, services, jobs, config
│   ├── ml/              Elo, features, train, backtest, SHAP explainability
│   ├── data_pipeline/   seeds + nflverse/odds/weather/injury loaders
│   ├── tests/           pytest suite (39 tests)
│   └── README.md        every backend command
├── docker/              docker-compose.yml (Postgres 16)
├── .github/workflows/   CI: ruff + pytest, lint + build
├── PLANNING.md          scope, stack, roadmap
└── IMPLEMENTATION_PLAN.md
```

## Testing

```powershell
cd backend && .venv\Scripts\python -m pytest      # 39 tests
cd frontend && npm run lint && npm run build
```

CI runs both suites on every push/PR.

---

© 2026 Paymon Software · Not betting advice.
