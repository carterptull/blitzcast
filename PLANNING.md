# Blitzcast — v1 Planning

NFL Matchup Predictor

## Vision

An AI/ML-powered web app where a user picks two NFL teams and gets a
win-probability prediction (0-100%) with human-readable reasoning behind it.
Long-term this could grow into a broader fantasy football platform (start/sit
tool, weekly rankings, trade calculator, "NFL passport" for tracking games
attended), but **v1 scope is the matchup predictor only.**

Inspiration: [cfbpassport.com](https://cfbpassport.com/),
[FantasyPros](https://www.fantasypros.com/).

## v1 Scope

- User picks from the **2026 season's actual scheduled matchups only** —
  not an arbitrary hypothetical two-team picker. The schedule is set well
  in advance (e.g. fbschedules.com already lists it), so v1 is scoped to
  "predict this week's real games," not "simulate any pairing."
  Hypothetical/what-if matchups (useful once playoff seeding is uncertain
  and opponents aren't locked in yet) are an explicit future extension,
  not v1.
- App returns a win probability split (e.g. 63% / 37%) plus a written
  explanation of the key factors driving the prediction.
- Inputs considered: historical matchup performance, recent team form,
  home/away, rest days, Vegas betting lines, weather, injuries, prime-time
  vs. standard time slot.
- Team logos displayed alongside each matchup.
- **No user accounts/auth in v1** — public, read-only tool, nothing to log
  in for. Revisit if a feature actually requires per-user state (e.g.
  saved predictions, favorite teams) — flag it if that comes up rather
  than assuming it's still out of scope.

## Design & UX Notes

- **Visual direction**: mown-turf field texture (alternating green stripes)
  as the hero background rather than a flat green fill, scoreboard-style
  condensed sans for team names/numerals, serif for the AI reasoning copy
  (editorial "sports page" feel), monospace for stat rows. First mockup:
  see the Blitzcast design artifact from this planning session.
- **Theme toggle**: light/dark mode toggle (sun/moon icon), placed top
  right near the wordmark. Both themes are first-class — dark mode reads
  as a night game under lights (deeper stripes, brighter gold accent), not
  just an inverted palette.
- **Mobile-friendly**: the layout must collapse cleanly on small screens
  (stacked team cards instead of side-by-side, ticker grid reflows to 2
  columns, etc.) — this is a requirement, not a nice-to-have, since the
  app will be shared with friends who'll mostly open it on phones.
- **Support CTA**: a "Buy Me a Beer" button (Buy Me a Coffee, relabeled),
  bottom of the page — same pattern as the CFB Passport inspiration site.
  Link comes from `NEXT_PUBLIC_BUYMEACOFFEE_URL` (`frontend/.env.example`),
  filled in manually once the Buy Me a Coffee account exists.
- **Footer**: copyright line, the Buy Me a Beer button, and the app version
  number (see Versioning below) all live together in the page footer.
  Copyright line: "© 2026 Paymon Software".

## Branding

- Public-facing brand for the app is **Paymon Software** — no link to the
  real-name personal portfolio site from within Blitzcast. "Software" over
  "Inc."/"Incorporated" deliberately, since the latter implies an actual
  legal entity that doesn't exist. Buy Me a Coffee account should also be
  under "Paymon" for consistency.
- Git commits/GitHub remain under the maintainer's real name, which is
  what's actually checked for engineering credibility — the two identities
  don't need to be cross-linked.

## Versioning

SemVer (`MAJOR.MINOR.PATCH`). Per SemVer convention, `0.x.y` means initial
development — anything may change. Start at **`0.1.0-beta`**, bump `MINOR`
for new features and `PATCH` for fixes while in beta; cut **`1.0.0`** when
it's deployed live and considered a real v1. Single source of truth: a root
`VERSION` file, bumped by hand alongside `frontend/package.json`'s version
field at release time, displayed in the footer.

## ML Approach: statistical model + LLM narration (hybrid)

Chosen over a pure LLM-driven approach (weak ML signal, hard to validate) and
over a purely statistical model with no narration (less engaging UX).

- **Core model**: gradient boosting classifier (XGBoost or LightGBM)
  predicting win probability from engineered features. Deterministic,
  testable, explainable — this is the real ML engineering component.
- **Validation**: backtest season-by-season on held-out historical data.
  Track Brier score / log-loss and calibration (a 70%-confidence prediction
  should win ~70% of the time). This is the evidence that the model is
  actually good, not just plausible-sounding.
- **Explainability**: SHAP values per prediction to identify which features
  pushed the prediction toward one team.
- **LLM narration layer**: the trained model's output (win probability + top
  SHAP features) is passed to Claude to generate a natural-language
  explanation. The LLM never touches the actual prediction math — it only
  explains a deterministic result.

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind | Matchup picker, probability display, reasoning panel |
| ML/data backend | Python + FastAPI | Serves predictions; owns the ML pipeline |
| Database | Postgres (Docker locally → Cloud SQL or Supabase later) | Teams, games, odds, injuries, weather, cached predictions |
| ML tooling | pandas, scikit-learn, XGBoost/LightGBM, SHAP | Training, backtesting, explainability |
| LLM | Claude API | Reasoning narration only |
| Hosting (future) | Vercel (frontend) + Cloud Run (FastAPI) + Cloud SQL/Supabase | Leverages existing GCP familiarity |

Frontend and ML backend are separate services communicating over an internal
API — deliberately decoupled rather than a monolith.

## Data Sources (free tier)

- **Historical stats/schedules/rosters**: `nfl_data_py` (nflverse/nflfastR
  data) — play-by-play and schedule data back to 1999. No signup, no key.
- **Vegas odds**: [The Odds API](https://the-odds-api.com/) free tier
  (500 requests/month). Sign up at the-odds-api.com → "Get API Key" → free
  tier, no credit card. Env var: `ODDS_API_KEY`.
- **Weather**: [Visual Crossing](https://www.visualcrossing.com/weather-api)
  Timeline API, not OpenWeatherMap — OpenWeatherMap's free tier only covers
  current/forecast conditions, not historical, and historical weather is
  needed for backtesting past seasons. Visual Crossing's free tier includes
  historical data (1,000 records/day). Sign up → free account → key on
  account page. Env var: `VISUAL_CROSSING_API_KEY`. Skip for domed stadiums.
- **Injuries**: ESPN public (unofficial) endpoints or nflverse injury
  reports. No key needed, but "unofficial" means undocumented and subject to
  change without notice — worth caching aggressively and having nflverse as
  a fallback.
- **Logos**: ESPN CDN (`a.espncdn.com/i/teamlogos/nfl/500/<abbr>.png`). No
  key needed.
- **LLM narration**: Claude API via console.anthropic.com → create an API
  key. Env var: `ANTHROPIC_API_KEY`.

**Odds refresh cadence**: The Odds API's free tier (500 requests/month)
can't support per-user-request live calls. A scheduled job pulls odds once
daily for the current week's scheduled games and stores them in Postgres;
the app always reads cached odds from the DB, never calls the API directly
on a user request. Predictions for the week's games are similarly
generated by a batch job (not on-demand) once the input data (odds,
injuries, weather) is in — this keeps the app fast and keeps API usage
predictable and cheap.

## Feature List (v1 model)

**Team strength**
- Rolling Elo-style rating per team, updated after each game
- Offensive EPA/play and defensive EPA/play allowed, rolling avg (last 5 games)
- Point differential, last 5 games

**Recent form**
- Win % over last 5 games
- Turnover differential, last 3 games

**Schedule/rest**
- Days of rest since last game (captures short week / bye week advantage)
- Back-to-back road games flag

**Situational**
- Home/away
- Divisional matchup flag
- Prime-time flag (SNF/MNF/TNF)
- Week number / season stage

**Injuries**
- Starting QB status flag (out/doubtful) — disproportionately predictive on
  its own
- Aggregate injury severity score (weighted by position importance × report
  status)

**Weather** (null/skip when game is in a dome)
- Temperature, wind speed, precipitation flag

**Market signal**
- Vegas spread and moneyline-implied probability — used both as a model
  input and as the baseline the model is compared against during
  backtesting (beating or matching the market is a much stronger portfolio
  claim than a model that can't)

## Historical Data Window

Train on the **most recent 4 completed seasons** (~1,080 games). Pull **5
seasons of raw data**, not 4 — rolling features (last-5-games form, Elo)
need prior games to avoid being blank at the start of Week 1 of the earliest
training season, so the extra season only seeds the rolling stats and isn't
itself used as a training row.

## Database Schema (Postgres)

```
teams            (team_id PK, abbr, name, conference, division, stadium_id FK)
stadiums         (stadium_id PK, name, city, lat, lon, is_dome, surface)
games            (game_id PK, season, week, game_date, kickoff_time,
                  home_team_id FK, away_team_id FK, stadium_id FK,
                  is_primetime, is_divisional, home_score, away_score, status)
team_game_stats  (game_id FK, team_id FK, points, yards, epa_offense,
                  epa_defense, turnovers)          -- actuals, used to derive rolling features
team_ratings     (team_id FK, season, week, elo_rating)   -- weekly rolling snapshot
odds             (odds_id PK, game_id FK, source, spread_home,
                  moneyline_home, moneyline_away, total, captured_at)
weather          (game_id FK, temp_f, wind_mph, precipitation, conditions, captured_at)
injuries         (injury_id PK, game_id FK, team_id FK, player_name,
                  position, status, report_date)
predictions      (prediction_id PK, game_id FK, model_version,
                  home_win_prob, predicted_at, shap_top_features JSONB, llm_narrative TEXT)
```

`team_game_stats` and `team_ratings` exist so rolling features can be
computed incrementally rather than recomputed from scratch each time.

## Local Dev Environment

Install **Docker Desktop** and run Postgres via `docker-compose.yml` only —
run the Next.js and FastAPI apps natively on the host for fast iteration/
hot-reload. Docker is reserved for Postgres now, and for containerizing the
app code itself later at deploy time.

## Repo Structure (monorepo)

```
blitzcast/
├── frontend/           Next.js app (TypeScript, Tailwind, App Router)
├── backend/
│   ├── app/             FastAPI routes (prediction API) — main.py has a /health check
│   ├── ml/              feature engineering, training, backtesting, SHAP
│   ├── data_pipeline/   scripts pulling from nfl_data_py, Odds API, weather, ESPN
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example     copy to .env and fill in real keys (gitignored)
├── docker/
│   └── docker-compose.yml   Postgres only, for now
├── PLANNING.md
├── CLAUDE.md
└── .gitignore
```

Scaffolding status: frontend (`create-next-app`) and backend (FastAPI skeleton
with a working `/health` route) have both been created and smoke-tested
locally. `docker-compose.yml` defines the Postgres service but hasn't been
started yet (needs Docker Desktop installed).

## Cost Outlook

- **Now (local dev)**: $0 — Docker Compose Postgres, free-tier APIs.
- **Once deployed**: Vercel free tier + Cloud Run free tier likely covers low
  traffic; Cloud SQL smallest instance ~$8-10/mo (or stay on Supabase free
  tier to avoid this); Claude API usage is a few cents per hundred narrated
  predictions. Realistic total: **$0-15/month**.

## Testing & CI

Even for a solo project, this is worth doing well — it's a strong, low-effort
recruiter signal and catches regressions as the ML pipeline evolves.

- **Backend**: pytest for the FastAPI app and the ML pipeline (feature
  engineering, backtesting utilities).
- **CI**: GitHub Actions workflow running lint + tests on push/PR.
- Frontend testing (component tests, etc.) can follow once there's UI worth
  testing — not blocking early phases.

## Phased Build Order

1. **Data pipeline** — pull historical games/stats/schedules into Postgres;
   build a clean training dataset.
2. **Model** — train, backtest, calibrate; save model artifact + SHAP
   explainer.
3. **Prediction API** — FastAPI endpoint: given two teams + date, return
   probability + feature breakdown.
4. **LLM narration layer** — wrap model output into a reasoning paragraph.
5. **Frontend** — matchup picker, logos, probability gauge, reasoning panel.
6. **Deploy** — Vercel + Cloud Run + managed Postgres.

## Explicitly Out of Scope for v1

- Player-vs-player start/sit comparisons (fantasy football).
- "NFL passport" game-tracking/sharing feature.
- Weekly fantasy rankings (best ball / dynasty).
- Fantasy trade calculator or trade recommendations.

These are worth revisiting once v1 is live and stable.
