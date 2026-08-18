# Blitzcast

An AI/ML-powered matchup predictor for **NFL and college football** by
**Paymon Software**. Pick a 2026 matchup, get a win probability (0–100%)
plus a broadcaster-style explanation of the key factors behind it, built on
a trained, calibrated XGBoost model with SHAP explainability. Claude
narrates the model's output; it never makes the prediction.

**Version: 1.0.0** (see
[CHANGELOG](./CHANGELOG.md) and [releases](https://github.com/carterptull/blitzcast/releases))

Technical decision log: [DECISIONS.md](./DECISIONS.md) · Release history:
[CHANGELOG.md](./CHANGELOG.md) · Vulnerability reporting:
[SECURITY.md](./SECURITY.md) · Backend commands:
[backend/README.md](./backend/README.md) · License:
[LICENSE](./LICENSE)

## How it works

1. **Data pipeline** (`backend/data_pipeline/`) pulls schedules, results,
   play-by-play EPA, injuries, odds, and weather into Postgres: nflverse
   (via `nflreadpy`) for history, The Odds API + Visual Crossing + ESPN for
   the current week.
2. **Model** (`backend/ml/`): XGBoost home-win classifier over 20
   leakage-safe features (Elo, rolling EPA/form, rest, injuries, weather,
   market), Platt-calibrated, walk-forward backtested against the Vegas
   closing line.
3. **API** (`backend/app/`): FastAPI serves cached predictions; a weekly
   batch job (features → predict → SHAP → narrate → upsert) does the work.
4. **Narration**: Claude (Haiku 4.5) turns the probability + top SHAP
   factors into 2–4 sentences of radio-broadcaster color. Guardrailed: it
   can never change or invent the numbers.
5. **Frontend** (`frontend/`): Next.js + Tailwind, with a week slate,
   turf-hero matchup pages, light/dark themes, mobile-first.

## Finished games and the season record

Once a game is final, its card and matchup page show the actual score and
a "Called it" / "Missed" verdict badge for the model's pick. Each slate
also opens with a season-to-date record banner: model accuracy shown next
to the market's accuracy over the same graded games, never the model's
number by itself, and it stays hidden behind a "not enough games yet"
message below 10 graded games (`GET /api/record`). A separate `/how-it-works`
page, linked from the footer, walks through the model's inputs, the
leakage rule, the LLM boundary, and this same honest comparison in more
detail.

Both slates also support filtering by game status (all / completed /
upcoming) via `?status=`, and surface the week's largest gaps between the
model's win probability and the market's as a curiosity, not a betting
signal.

## Backtest results

Walk-forward by season (train strictly on prior seasons), compared to
de-vigged closing moneylines:

| Season | Games | Model Brier | Vegas Brier | Model Acc | Vegas Acc |
|---|---|---|---|---|---|
| 2023 | 285 | 0.2415 | 0.2186 | 0.604 | 0.677 |
| 2024 | 285 | 0.2099 | 0.2010 | 0.691 | 0.705 |
| 2025 | 285 | 0.2173 | 0.2104 | 0.656 | 0.663 |
| **All** | 855 | **0.2229** | **0.2100** | 0.650 | 0.682 |

Using only public data the model lands in the neighborhood of the closing
line without beating it: about 3 points of accuracy behind Vegas overall,
and behind on Brier in every season. Full report and calibration plot:
`backend/ml/reports/`.

CFB has its own Elo/model/calibration, walk-forward against de-vigged CFBD
closing lines (FBS-vs-FBS games only; FBS-vs-FCS mismatches are predicted
but excluded from these metrics):

| Season | Games | Model Brier | Vegas Brier | Model Acc | Vegas Acc |
|---|---|---|---|---|---|
| 2023 | 755 | 0.1842 | 0.1685 | 0.695 | 0.739 |
| 2024 | 757 | 0.1844 | 0.1781 | 0.717 | 0.727 |
| 2025 | 763 | 0.1754 | 0.1719 | 0.738 | 0.748 |
| **All** | 2275 | **0.1813** | **0.1729** | 0.717 | 0.738 |

Full report: `backend/ml/reports/backtest_cfb.md`.

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

# NFL pipeline
.venv\Scripts\python -m data_pipeline.seed
.venv\Scripts\python -m data_pipeline.backfill
.venv\Scripts\python -m ml.train --sport nfl
.venv\Scripts\python -m app.jobs.predict_week --sport nfl

# CFB pipeline (independent of NFL, same DB)
.venv\Scripts\python -m data_pipeline.seed_cfb
.venv\Scripts\python -m data_pipeline.backfill_cfb
.venv\Scripts\python -m ml.train --sport cfb
.venv\Scripts\python -m data_pipeline.refresh_schedule_cfb   # syncs current season
.venv\Scripts\python -m app.jobs.predict_week --sport cfb

.venv\Scripts\python -m uvicorn app.main:app --reload   # http://localhost:8000

# 3. Frontend (new terminal)
cd frontend
npm install
copy .env.example .env.local      # set NEXT_PUBLIC_BUYMEACOFFEE_URL etc.
npm run dev                        # http://localhost:3000, tabs at /nfl and /cfb
```

In-season weekly refresh (odds → weather → injuries → predictions):

```powershell
.venv\Scripts\python -m data_pipeline.refresh_week        # NFL
.venv\Scripts\python -m data_pipeline.refresh_week_cfb     # CFB
```

**No API keys yet?** Everything still runs: refresh jobs skip politely,
narration falls back to the factor list, and the frontend has a full mock
mode (`NEXT_PUBLIC_USE_MOCK=1`) plus the backend's `BLITZCAST_MOCK=1`.

## Repo structure

```
blitzcast/
├── frontend/            Next.js 16 + TypeScript + Tailwind v4 (App Router)
│                        routes: /nfl, /cfb, /[sport]/matchup/[gameId],
│                        /how-it-works
├── backend/
│   ├── app/             FastAPI: routers, schemas, services, jobs, config
│   ├── ml/              Elo, features, train, backtest, SHAP explainability
│   │                    (per-sport artifacts: ml/artifacts/, ml/artifacts/cfb/)
│   ├── data_pipeline/   seeds + nflverse/CFBD/odds/weather/injury loaders
│   │                    (NFL and *_cfb.py CFB counterparts)
│   ├── tests/           pytest suite (148 tests)
│   └── README.md        every backend command
├── docker/              docker-compose.yml (Postgres 16)
├── .github/workflows/   CI: ruff + pytest, lint + build
├── DECISIONS.md         technical decision log
├── CHANGELOG.md         release history
├── SECURITY.md          vulnerability reporting policy
└── LICENSE              MIT license
```

## Testing

```powershell
cd backend  && .venv\Scripts\python -m pytest     # 148 tests
cd frontend && npm test                           # 114 tests
cd frontend && npm run lint && npm run build
```

CI runs both suites on every push/PR.

## Known limitations

- **CFB postseason is never loaded.** `cfbd.load_games` hardcodes
  `seasonType="regular"`, so bowl and playoff results never arrive.
  Pre-existing, not addressed by the finished-games work.
- **No live/in-progress game state.** A game is only ever `scheduled` or
  `final`; there's no in-progress score.
- **No season selector.** The slate always shows the current season
  (2026). Historical, backfilled data (2023-2025) is reachable only via a
  direct matchup URL by game id, not through slate navigation. Deliberate
  scope decision, not a bug.
- **`--gold-turf` fails AA contrast** (about 3.27:1) against the turf
  gradient's lighter stop. Confirmed by two independent reviews; a
  brand-token decision to leave as-is for now, not a feature defect.
- ~~No automated regression test on the pick'em / exact-0.5 market
  exclusion~~ Resolved: `test_record_excludes_pickem_market_lines_from_both_counts`
  (backend) and `test_get_record_excludes_pickem_market_lines_from_both_counts`
  (mock mode) now guard the real bug this was tracking (a pick'em market line
  was being scored as a market loss instead of excluded, affecting roughly
  22 games in the current historical data).

## License

Released under the MIT License. See [LICENSE](./LICENSE) for the full
text.

---

© 2026 Paymon Software · Not betting advice.
