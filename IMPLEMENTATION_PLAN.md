# Blitzcast — v0.1.0 Implementation Plan

> **Audience:** this document is a hand-off to Fable 5 for implementation.
> It is prescriptive about architecture, data flow, and contracts, but
> **Fable is explicitly invited to improve on it** — especially the frontend
> look/feel/presentation, and any gaps flagged inline. Where this plan and
> good judgment conflict, use judgment and leave a note. Read
> [PLANNING.md](./PLANNING.md) first; it holds the shared context (scope,
> tech stack, DB schema, feature list, branding, versioning) that this plan
> builds on and does not repeat.

## 0. How to read this plan

- **Target release:** `v0.1.0-beta` — runs **locally only**. Public deploy is
  out of scope for this version (deployment notes are included at the end as
  forward-looking, not v0.1.0 work).
- **Scope reminder:** predicts the **2026 NFL season's real scheduled
  matchups only**. No hypothetical pairings, no user accounts/auth.
- **Verification callouts:** anywhere you see **[VERIFY]**, confirm the exact
  current function/endpoint signature before relying on it — this plan was
  written from knowledge that may lag the libraries. Don't guess; check.
- **Secrets:** the user (Paymon) will paste API keys and the Buy Me a Coffee
  URL into `.env` files manually. Never hard-code them; never commit them.
- **Do not commit or push** unless the user explicitly asks.

### Environment / secrets summary

| Var | File | Purpose |
|---|---|---|
| `DATABASE_URL` | `backend/.env` | Postgres connection (default in `.env.example`) |
| `ODDS_API_KEY` | `backend/.env` | The Odds API |
| `VISUAL_CROSSING_API_KEY` | `backend/.env` | Visual Crossing weather |
| `ANTHROPIC_API_KEY` | `backend/.env` | Claude API narration |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/.env` | Backend base URL (default `http://localhost:8000`) |
| `NEXT_PUBLIC_BUYMEACOFFEE_URL` | `frontend/.env` | Buy Me a Beer button link |

---

## Phase 0: Foundations (do this first)

Before any feature work, lock the plumbing so every later phase has a stable
base.

1. **Config layer** — `backend/app/config.py` using `pydantic-settings`
   (`BaseSettings`) to load the env vars above. One `Settings` singleton
   imported everywhere. Fail fast with a clear error if a required key is
   missing at startup (except keys only needed by specific jobs — those can
   validate lazily).
2. **DB session** — `backend/app/db.py`: SQLAlchemy 2.x engine + session
   factory reading `DATABASE_URL`. Provide a FastAPI dependency
   (`get_db()`), and a plain context-managed session for pipeline scripts
   (which run outside FastAPI).
3. **ORM models** — `backend/app/models.py` (or a `models/` package):
   SQLAlchemy models for every table in the PLANNING.md schema (teams,
   stadiums, games, team_game_stats, team_ratings, odds, weather, injuries,
   predictions). Use `mapped_column` / typed `Mapped[...]` style.
4. **Migrations** — initialize **Alembic** (`backend/alembic/`). First
   migration creates all tables. Every schema change after this is a new
   migration, never a manual edit. [GAP] Fable: add a `make`/script shortcut
   or README note for `alembic upgrade head`.
5. **Dependency management** — `backend/requirements.txt` exists but consider
   splitting into `requirements.txt` (runtime) and `requirements-dev.txt`
   (pytest, ruff, etc.), or moving to `pyproject.toml` + `uv`/`pip-tools`.
   Fable's call — just keep it reproducible and documented.
6. **Lint/format** — add `ruff` (lint + format) for Python and rely on the
   Next.js ESLint config for the frontend. Wire both into CI (Phase 6).
7. **Makefile / task runner** *(recommended, optional)* — a root `Makefile`
   or `scripts/` with the common commands (`db-up`, `migrate`, `backfill`,
   `predict-week`, `api`, `web`, `test`). Cuts the README to a few verbs and
   is a nice recruiter-facing touch.

**Definition of done:** `alembic upgrade head` against the Dockerized
Postgres creates every table; `uvicorn app.main:app` still serves `/health`;
`pytest` runs (even with near-zero tests) green.

---

## Phase 1: Data Pipeline

**Goal:** populate Postgres with (a) five seasons of historical data to train
on, and (b) the 2026 schedule + weekly-updating inputs (odds, weather,
injuries) for live prediction.

Everything here lives in `backend/data_pipeline/`. Design every loader as an
**idempotent upsert** (re-running never duplicates rows) keyed on natural
keys (e.g. nflverse `game_id`), so the weekly refresh and re-runs are safe.

### 1.1 Reference / seed data (static, do once)

- **Teams** (32) and **stadiums**: mostly static. Recommended: a checked-in
  seed file (`backend/data_pipeline/seeds/stadiums.json` and `teams.json`)
  with `abbr`, name, conference, division, and per-stadium `lat`, `lon`,
  `is_dome`, `surface`. `nfl_data_py.import_team_desc()` **[VERIFY]** gives
  team metadata and logo URLs; stadium lat/lon and dome flags are not cleanly
  in nflverse, so hand-curate the 32-row seed (it's a one-time table). This
  seed powers weather (lat/lon), dome-skip logic, and divisional-matchup
  detection.
- A `seed` script loads these into `teams` and `stadiums`.

### 1.2 Historical backfill (run once)

Pull **5 seasons** (train on the most recent 4; the earliest seeds rolling
features — see PLANNING.md "Historical Data Window"). Use `nfl_data_py`
**[VERIFY all function names/signatures — the package API shifts]**:

| Data | Likely function | Populates |
|---|---|---|
| Schedules + results | `import_schedules([years])` | `games` (teams, date, kickoff, home/away score, week, season) |
| Play-by-play (for EPA) | `import_pbp_data([years])` | derive `team_game_stats.epa_offense/epa_defense` |
| Weekly team/player stats | `import_weekly_data([years])` **[VERIFY]** | `team_game_stats` (points, yards, turnovers) |
| Injuries (historical) | `import_injuries([years])` **[VERIFY]** | `injuries` (historical, for feature building) |
| Team metadata | `import_team_desc()` | `teams`, logo refs |

**EPA derivation:** `import_pbp_data` returns play-level rows with an `epa`
column and `posteam`/`defteam`. For each game+team: `epa_offense = mean(epa
where posteam == team)`, `epa_defense = mean(epa where defteam == team)`.
Aggregate to one `team_game_stats` row per (game, team). [VERIFY] column
names (`posteam`, `defteam`, `epa`, `game_id`) against a real sample — print
`df.columns` first.

**Primetime & divisional flags on `games`:** derive primetime from
kickoff time / weekday (SNF/MNF/TNF) — nflverse schedules often include a
`gameday`/`gametime`/`weekday` and sometimes a national-TV field **[VERIFY]**.
Divisional = both teams share conference+division (from the teams table).

**Historical odds:** The Odds API free tier does **not** give deep history
cheaply. For backfilling the *training* set's market feature, prefer
nflverse — `import_schedules` includes closing `spread_line` and
`total_line` and moneyline-ish fields for past seasons **[VERIFY]**. Use
those for historical Vegas features; reserve The Odds API strictly for
*current* 2026 games. Document this split clearly so the feature is computed
consistently (convert spread→implied prob, or use moneyline where present).

### 1.3 Recurring 2026 refresh jobs

These run on a schedule during the season. For **local v0.1.0**, implement
each as a CLI-runnable Python script (`python -m data_pipeline.refresh_odds`
etc.) plus one orchestrator (`refresh_week.py`) that runs them in order.
Scheduling locally can be manual or Windows Task Scheduler; **APScheduler**
or cron is the deploy-time answer — don't over-build scheduling for local.

1. **Schedule sync** — pull the 2026 schedule into `games` (once it's
   published; upsert so bye weeks / flex changes update). **If `nfl_data_py`
   doesn't yet expose the full 2026 schedule** at build time, fall back to a
   **one-time import from ESPN's schedule endpoint or a web-sourced
   schedule** (e.g. an fbschedules-style export), routed through the
   canonical `abbr` mapping. Either way the result is the same `games` rows;
   treat the source as swappable.
2. **Odds refresh** (`ODDS_API_KEY`) — **[VERIFY]** endpoint
   `GET https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds`
   with params `regions=us`, `markets=h2h,spreads,totals`,
   `oddsFormat=american`, `apiKey=...`. Map each game to an `odds` row
   (`spread_home`, `moneyline_home`, `moneyline_away`, `total`,
   `captured_at`, `source`). **Budget discipline:** free tier = 500
   req/month; the response returns all games in one call, so **one call/day**
   is plenty (~30/month). Match Odds-API team names to our `abbr` via a
   mapping table (their names are full names — build a name→abbr dict).
3. **Weather refresh** (`VISUAL_CROSSING_API_KEY`) — **[VERIFY]** Timeline
   API: `GET https://weather.visualcrossing.com/VisualCrossingWebServices/
   rest/services/timeline/{lat},{lon}/{date}` with `key=...`,
   `unitGroup=us`. **Skip domed stadiums entirely** (write NULLs / a
   `is_dome` sentinel). For future kickoffs it returns forecast; for past
   dates, historical actuals. Map temp, wind, precip → `weather` row.
   Budget: 1,000 records/day free — trivially within limits (~16 games/wk).
4. **Injury refresh** — ESPN unofficial endpoint **[VERIFY]** (e.g. the
   `site.api.espn.com/apis/site/v2/sports/football/nfl/...` family) for
   current injury/status, **with `nfl_data_py` injuries as the documented
   fallback** if ESPN's shape changes. Map to `injuries` (player, position,
   status, report_date). Critically capture **starting-QB status** (needed
   for the single most predictive injury feature).

**Orchestrator flow** (`refresh_week.py`): schedule sync → odds → weather →
injuries → (then Phase 3's prediction batch). Log a concise summary per step
(rows upserted, API calls used). Make each step independently re-runnable.

### 1.4 Gaps / risks (Phase 1)

- **[RISK] 2026 hasn't been played** — at season start `team_game_stats` for
  2026 is empty, so in-season rolling features are thin early. Handled in
  Phase 2 (cold-start), but the pipeline must not error on empty windows.
- **[RISK] ESPN endpoints are unofficial** — cache aggressively, wrap in
  try/except, fall back to nflverse, and never let an injury-fetch failure
  break the whole refresh.
- **[GAP] Team-name matching** across sources (Odds API full names, nflverse
  abbrs, ESPN) — build one canonical `abbr` mapping module and route every
  external name through it. This bites hard if left implicit.
- **[GAP] Data-freshness/audit** — consider a tiny `pipeline_runs` table or
  structured log so you can see when each source last updated. Optional for
  v0.1.0 but cheap insurance.

---

## Phase 2: ML Model

**Goal:** a calibrated home-win-probability model, backtested against the
Vegas baseline, with per-game SHAP explanations. Lives in `backend/ml/`.

### 2.1 Feature engineering (`ml/features.py`)

Build a function that, given a target game (season, week, home, away),
produces a feature vector using **only information available before
kickoff**. This anti-leakage rule is the single most important correctness
property of the whole model — every rolling stat must be computed **as of the
prior week**, never including the game being predicted or anything after it.

Features (implementing PLANNING.md's list):

- **Elo rating (home & away, pre-game):** implement a standard NFL Elo.
  Recommended starting constants (tune later): `K = 20`, home-field advantage
  `≈ 55` Elo points added to the home team's rating in the expectation,
  logistic scale `400`. Update after each game:
  `expected_home = 1 / (1 + 10^(-(elo_home + HFA - elo_away)/400))`, then
  `elo_home += K * (result - expected_home)` (result ∈ {1,0}). **Between
  seasons, regress each team toward the mean** (`elo = 1500 + 0.75*(elo -
  1500)` is a common carry-forward). Persist weekly snapshots to
  `team_ratings` so the API/feature builder reads pre-computed ratings
  instead of replaying history each call. **[VERIFY]** — optionally seed
  from nflverse-provided Elo if available; otherwise compute from results.
- **Rolling EPA/play** (offense and defense), last 5 games, per team,
  as-of prior week.
- **Point differential** (last 5), **win %** (last 5), **turnover
  differential** (last 3) — all as-of prior week.
- **Rest:** days since each team's previous game; `short_week` and
  `off_bye` flags. **Back-to-back road** flag.
- **Situational:** home/away is implicit (features are home-minus-away
  deltas — see below), `is_divisional`, `is_primetime`, `week_number`.
- **QB status flag:** starting QB out/doubtful (from injuries).
- **Injury severity score:** weighted sum of players out/questionable by
  positional importance (QB >> skill/OL >> depth). Define the weights in one
  place and document them.
- **Weather:** temp, wind, precip flag (0/dome-neutral when indoors).
- **Market:** Vegas spread and moneyline-implied win prob (de-vig if you want
  to be rigorous — at minimum note that raw implied probs sum >1).

**Representation:** prefer **home-minus-away difference features** (e.g.
`elo_diff`, `epa_off_diff`, `rest_diff`) plus the few absolute/context
features (primetime, divisional, week, weather). Differences make the model
smaller, more stable, and more interpretable, and they make the SHAP story
cleaner ("+0.14 from home Elo edge").

**Output:** a tidy `DataFrame` — one row per historical game with all
features + the binary target `home_win` — cached to
`backend/ml/data/features.parquet` (gitignored) so training doesn't re-derive
every run.

### 2.2 Model & target

- **Target:** `home_win` (1 if home score > away score).
- **Model:** **XGBoost** (`XGBClassifier`). Justified over LightGBM here only
  by marginally better small-data robustness and ubiquity/recruiter
  recognition — either is fine; Fable may switch to LightGBM. Start modest to
  avoid overfitting ~1,080 rows: `max_depth=3–4`, `n_estimators` tuned via
  early stopping, `learning_rate≈0.03–0.05`, `subsample≈0.8`,
  `colsample_bytree≈0.8`, `min_child_weight` moderate. Use
  `eval_metric="logloss"`.
- **Probability calibration:** tree models are often miscalibrated. Wrap with
  isotonic or Platt scaling via a **time-aware** holdout (not random CV) —
  e.g. fit calibration on the most recent held-out season. Recommend
  isotonic if enough data, Platt (sigmoid) if sparse. Calibration is a core
  selling point of this project — treat reliability as a first-class metric,
  not an afterthought.

### 2.3 Backtest & validation (`ml/backtest.py`)

**Never random k-fold** — it leaks the future into the past. Use
**walk-forward / expanding-window** by season (and optionally by week):
train on seasons up to N, predict season N+1, roll forward. Report, on each
out-of-sample season:

- **Brier score** and **log-loss** (primary — these reward calibration).
- **Accuracy** and **AUC** (secondary, intuitive).
- **Calibration/reliability curve** (bin predicted prob vs. actual win rate)
  — save the plot to `backend/ml/reports/`.
- **Vegas baseline comparison** — the killer metric. Compute the same
  Brier/log-loss for the market's implied probabilities and put your model
  next to it. **"Matches or beats the closing line"** is the headline result
  for the README/portfolio; "clearly worse than Vegas" is still an honest,
  presentable result (the market is extremely hard to beat) — frame it as
  "approaches market accuracy using only public data."

Write the backtest summary to `backend/ml/reports/backtest.md` (a table +
the calibration plot) so it can be surfaced in the repo README later.

### 2.4 Explainability (`ml/explain.py`)

- **SHAP `TreeExplainer`** on the trained XGBoost model.
- For a given prediction, extract the **top N (≈4) features by |SHAP value|**
  with their **signed** contribution and a **human-readable label**
  (map `elo_diff` → "Team X's rating edge", `rest_diff` → "Rest advantage",
  etc. — keep a `FEATURE_LABELS` dict).
- Emit a compact structure the API/LLM layer consumes, e.g.
  `[{"feature": "home_field_cold", "label": "Home field, cold-weather kickoff", "value": 0.14, "direction": "home"}, ...]`.
  Get the sign convention right so "+" always means "toward the favored
  team" in the narrative.

### 2.5 Model artifact & versioning (`ml/train.py`)

- Serialize with **joblib** to `backend/ml/artifacts/model_<version>.joblib`
  — a bundle containing: the fitted+calibrated model, the ordered feature
  list, the `FEATURE_LABELS`, the training window, and the backtest metrics.
- Also write `backend/ml/artifacts/latest.json` pointing at the current
  artifact + `model_version` string (e.g. `"0.1.0"`), so the API loads
  "latest" without code changes.
- `model_version` is written into every `predictions` row for traceability.
- Artifacts are **gitignored** (already covered by `*.joblib` in
  `.gitignore`); training is reproducible from code + DB.

### 2.6 Cold-start for the 2026 season (**important, easy to miss**)

Because 2026 is unplayed, Weeks 1–4 have little/no in-season signal:

- **Carry Elo forward** from end of 2025, regressed to the mean (see 2.1).
  This gives Week 1 a real prior instead of a flat 50/50. **Confirmed:** use
  nflverse historical `spread_line`/`total_line` for the *training* market
  feature and reserve The Odds API strictly for current 2026 games (keeps
  usage inside the free tier).
- **Rolling EPA/form:** for early weeks, **blend** the (empty/thin) 2026
  window with a **prior** — the team's late-2025 rolling values, decaying the
  prior's weight as 2026 games accumulate (e.g. weight prior by
  `max(0, (4 - games_played)/4)`).
- **Market feature is most reliable early** — the Vegas line already encodes
  offseason changes; lean on it for Weeks 1–3 and let learned form take over
  as the season fills in.
- Document this behavior; add a test that Week-1 2026 predictions are
  produced without error and aren't degenerate (not all 50%).

### 2.7 Gaps / risks (Phase 2)

- **[RISK] Small data (~1,080 games):** keep the model shallow, prefer
  difference features, lean on regularization and calibration. Resist
  feature-count creep.
- **[RISK] Leakage** is the classic killer — add an explicit test that a
  feature row for game G contains no data dated ≥ G's kickoff.
- **[GAP] Feature store vs. recompute:** `team_ratings` is persisted, but
  decide whether rolling EPA/form is precomputed weekly into a table or
  derived on demand. Precomputing keeps the prediction batch fast and
  auditable — recommended.
- **[GAP] Retrain cadence:** for v0.1.0, retrain manually (a documented
  command). In-season weekly retrain is a later nicety.

---

## Phase 3: Prediction API

**Goal:** a FastAPI service that serves **cached** predictions + schedule data
to the frontend. It does **not** run the model per request — a batch job
(3.3) writes predictions to Postgres; the API reads them. Lives in
`backend/app/`.

### 3.1 Structure

```
backend/app/
├── main.py            # FastAPI app, CORS, router registration, /health
├── config.py          # pydantic-settings (Phase 0)
├── db.py              # engine/session (Phase 0)
├── models.py          # SQLAlchemy ORM (Phase 0)
├── schemas.py         # Pydantic response models (the API contract)
├── routers/
│   ├── schedule.py    # weeks + games
│   ├── games.py       # games by week
│   ├── predictions.py # prediction detail
│   └── teams.py       # team metadata/logos
└── services/
    └── predictions.py # read-side query helpers
```

Enable **CORS** for the Next.js origin (`http://localhost:3000` in dev; make
it configurable). Keep routes thin; put queries in `services/`.

### 3.2 Endpoints & contract (the frontend builds against this)

All responses JSON; all money/prob numbers as numbers, not strings. Use
`float` win probs in `[0,1]` (frontend formats as %). **[GAP]** Fable: add
OpenAPI tags/descriptions — FastAPI gives you `/docs` for free; make it
presentable.

- **`GET /api/teams`** → list of
  `{ id, abbr, name, conference, division, logo_url }`.
  `logo_url` = `https://a.espncdn.com/i/teamlogos/nfl/500/<abbr>.png`.

- **`GET /api/schedule?season=2026`** → weeks with their games (light
  payload for the week selector):
  ```json
  {
    "season": 2026,
    "weeks": [
      { "week": 1, "games": [
        { "game_id": "...", "kickoff": "2026-09-10T20:20:00Z",
          "home": {"abbr":"KC","name":"Chiefs"},
          "away": {"abbr":"BUF","name":"Bills"},
          "is_primetime": true, "status": "scheduled",
          "has_prediction": true }
      ]}
    ]
  }
  ```

- **`GET /api/games?week=1&season=2026`** → the same game objects for one
  week (convenience for the list view).

- **`GET /api/predictions/{game_id}`** → the full matchup detail the hero +
  reasoning panel render:
  ```json
  {
    "game_id": "...",
    "season": 2026, "week": 1,
    "kickoff": "2026-09-10T20:20:00Z",
    "venue": {"name":"Arrowhead Stadium","city":"Kansas City","is_dome":false},
    "is_primetime": true, "is_divisional": false,
    "home": {"abbr":"KC","name":"Chiefs","record":"0-0","logo_url":"...","win_prob":0.63},
    "away": {"abbr":"BUF","name":"Bills","record":"0-0","logo_url":"...","win_prob":0.37},
    "odds": {"spread_home":-2.5,"moneyline_home":-140,"moneyline_away":120,"total":48.5},
    "weather": {"temp_f":34,"wind_mph":12,"precipitation":false,"conditions":"Clear"},
    "factors": [
      {"label":"Home field, cold-weather kickoff","value":0.14,"direction":"home"},
      {"label":"Offensive EPA/play, last 5 games","value":0.09,"direction":"home"}
    ],
    "narrative": "Kansas City's edge is a rest-and-health story ...",
    "model_version": "0.1.0",
    "predicted_at": "2026-09-08T12:00:00Z"
  }
  ```
  `win_prob` values sum to 1.0. `factors` is the SHAP top-N (signed, labeled).
  `narrative` may be `null` if LLM generation failed — frontend must degrade
  gracefully (show factors without prose).

**Error handling:** 404 for unknown `game_id`; a clear "prediction not yet
generated" state (e.g. game exists but no prediction row) — return the game
meta with `factors: []`, `narrative: null`, and a `prediction_status` field
so the UI can say "prediction pending."

### 3.3 Prediction orchestration (batch, not per-request)

A job (`backend/app/jobs/predict_week.py` or under `data_pipeline/`) that,
after the weekly data refresh, for each upcoming game:

1. Build the feature vector (Phase 2 `features.py`).
2. `model.predict_proba` → `home_win_prob`.
3. SHAP → top factors (Phase 2 `explain.py`).
4. LLM narrate (Phase 4) → `narrative`.
5. **Upsert** a `predictions` row (`game_id`, `model_version`,
   `home_win_prob`, `shap_top_features` JSONB, `llm_narrative`,
   `predicted_at`).

Idempotent on `(game_id, model_version)`. The full weekly chain is: Phase 1
refresh → this batch → API serves fresh rows. Provide a CLI entrypoint and
log a per-game summary.

### 3.4 Gaps / risks (Phase 3)

- **[GAP] Records/standings:** the detail response shows team records — derive
  from `games` results as-of the game, or compute in the batch job. Decide
  where and keep it leakage-safe (record *entering* the game).
- **[GAP] Timezone:** store UTC, send ISO-8601 with offset; let the frontend
  localize. Be explicit and consistent.
- **[RISK] Stale predictions:** if odds/injuries move after generation,
  re-running the batch upserts fresh rows — document that the batch is the
  refresh mechanism.

---

## Phase 4: LLM Narration Layer

**Goal:** turn the deterministic model output into 2–4 sentences of
plain-language reasoning. **The LLM never computes or alters the
probability** — it only explains numbers it's handed. Lives in
`backend/app/services/narrate.py` (called by the 3.3 batch job).

> **[VERIFY] before coding:** open the `claude-api` skill/reference for
> current model IDs, SDK usage, and pricing. Do not hard-code a model ID from
> memory — confirm it.

### 4.1 Model choice

Short, structured, high-volume-ish narration → favor a **fast, cheap** model.
Recommended: **`claude-haiku-4-5-20251001`** (Haiku 4.5) as the default for
cost/latency; allow overriding to **`claude-sonnet-5`** via config if
narrative quality needs a bump. Make the model ID a setting, not a literal.

### 4.2 Prompt design

- **System prompt:** establish the role, **voice**, and the hard guardrail.
  **Voice = an excited radio play-by-play broadcaster** — stat-dense and
  detailed but delivered with energy and fun, not a dry analyst. Think
  color-commentary that name-drops the real numbers. Guardrail: "You are
  narrating a football win-probability prediction produced by a statistical
  model, in the voice of an energetic radio play-by-play broadcaster — fun,
  vivid, and packed with the specific stats you're given. You are given the
  probability and the top contributing factors. Never state a different
  probability than the one provided. Never invent stats not given. Keep it to
  2–4 sentences, exciting but grounded in the real numbers, no betting
  advice." Keep the energy from tipping into inventing facts — the guardrail
  and the "use only provided numbers" rule still bind.
- **User content:** a compact **structured** payload (JSON-ish) — teams,
  `home_win_prob`, the signed labeled `factors`, and a few key raw stats
  (spread, rest, QB status, weather) for color. Ask for prose that leads with
  the favored team and explains *why* using the given factors.
- **Output:** plain text (2–4 sentences). No JSON needed. Trim/validate
  length; strip stray markdown.

### 4.3 Guardrails, caching, cost, fallback

- **Guardrail check:** optionally verify the narrative doesn't contain a
  percentage that contradicts `home_win_prob` (cheap regex sanity check); if
  it does, regenerate once or fall back.
- **Caching:** store `llm_narrative` in the `predictions` row. **Never
  regenerate on read.** Regenerate only when the batch re-runs for a game
  (inputs changed).
- **Cost:** a few sentences × ~16 games/week is negligible (well under a cent
  per game on Haiku). Confirm current pricing in the `claude-api` reference.
- **Fallback:** if the API errors/times out, write `llm_narrative = null` and
  proceed — the UI shows the factor list without prose. One retry with
  backoff before giving up. A failed narration must never block a prediction.

### 4.4 Gaps / risks (Phase 4)

- **[RISK] Hallucinated specifics** — mitigate by passing only real stats and
  instructing "use only the provided numbers." Keep the factor labels
  self-describing so the model has little room to invent.
- **[GAP] Tone/voice** — Fable may draft 2–3 example narratives to pin the
  house style, and include them as few-shot examples if quality wobbles.

---

## Phase 5: Frontend

**Goal:** a polished, mobile-friendly Next.js app that browses the 2026
season's matchups and renders each prediction in the established
green-field visual language. Lives in `frontend/` (Next.js + TS + Tailwind,
App Router, `src/`). **Fable: you own the presentation — elevate it.** The
fixed constraints are branding, the mown-field concept, theming, and the
footer; everything else (micro-interactions, exact spacing, component polish)
is yours to make great.

### 5.1 Design language (honor; refine freely)

From the mockup built this session (see the Blitzcast design artifact):

- **Turf hero:** alternating green mowing stripes (`#1b4332`/`#2e6f4c`), not
  a flat fill; faint hash-mark overlay. Reads as a field, not a green box.
- **Type roles:** condensed/heavy sans for scoreboard elements (team names,
  big % numerals); **serif** for the AI reasoning copy (editorial sports-page
  voice); **monospace** (tabular-nums) for stat rows/odds. **[VERIFY font
  loading]** — the app can use webfonts normally (unlike Artifacts);
  self-host or use `next/font` to avoid layout shift. **Font choice is
  Fable's call** — pick the condensed-sans / serif / mono trio you think
  looks best. Requirements: distinctive, **not** the generic defaults (no
  Arial/Calibri/Helvetica/Inter-as-safe-choice), but still highly readable
  and unambiguous. Aim for something with character that still reads
  instantly at a glance on a scoreboard.
- **Accent:** a single gold (`#b9822e` light) used sparingly — the split
  marker, key numbers, section accents. Don't spray it.
- **Team color as data:** the win-probability split bar uses each team's
  color; it doubles as the primary visual of who's favored.
- **Light palette:** bg `#f3f7f0`, surface `#fdfef9`, ink `#10241c`.
  **Dark = night game under lights:** deeper stripes, brighter gold, high
  legibility — design it as a first-class theme, not an inversion.

### 5.2 Routes / screens (v0.1.0)

Recommended: **list + detail within one cohesive flow.**

- **`/` (home):** a **WeekSelector** (defaults to the current/next 2026 week)
  + a responsive grid of **GameCard**s for that week (logos, kickoff,
  primetime badge, a compact win-prob hint). Clicking a card opens the
  matchup.
- **`/matchup/[gameId]` (detail):** the full hero + reasoning layout
  (the mockup). A dedicated route (not just a panel) so matchups are
  **shareable by URL** — important since the app is meant to be shared with
  friends. [GAP] Fable: add basic OpenGraph/meta per matchup for nice link
  previews (nice-to-have).

*(Rationale: a real route per matchup gives shareable links and clean mobile
back-nav; a modal/panel would sacrifice both. If Fable prefers a parallel-
route modal that also updates the URL, that's an acceptable upgrade.)*

### 5.3 Component breakdown

- `WeekSelector` — props: `weeks`, `selectedWeek`, `onChange`. Horizontal
  scrollable on mobile.
- `GameCard` — props: `game` (teams, kickoff, primetime, win-prob hint,
  `has_prediction`). Links to detail.
- `MatchupHero` — the turf hero: both `TeamColumn`s + `WinProbabilitySplit` +
  game meta row (date, primetime, venue, weather).
- `TeamColumn` / `TeamCrest` — logo (ESPN CDN), name, record, big win-% .
  `TeamCrest` falls back to a colored monogram if the logo 404s.
- `WinProbabilitySplit` — the two-color bar + gold marker; animates on load
  (respect `prefers-reduced-motion`).
- `StatTicker` — monospace row: spread, rest edge, QB status, EPA diff, etc.
  Reflows to 2 columns on mobile.
- `ReasoningPanel` — serif narrative + `FactorList`.
- `FactorList` — signed, labeled SHAP factors (mono weights, gold for + ).
  Renders even when `narrative` is null.
- `ThemeToggle` — sun/moon, top-right; persists to `localStorage`, respects
  `prefers-color-scheme` on first load.
- `Footer` — `© 2026 Paymon Software` · Buy Me a Beer button (🍺, href from
  `NEXT_PUBLIC_BUYMEACOFFEE_URL`, hidden/disabled gracefully if unset) ·
  version string from the root `VERSION` / `package.json` (`0.1.0-beta`).
- Loading & empty states — skeletons for cards/hero; a "prediction pending"
  state when a game has no prediction row yet.

### 5.4 Data fetching

- Base URL from `NEXT_PUBLIC_API_BASE_URL`. A thin `src/lib/api.ts` typed
  client mirroring the Phase 3 schemas (define matching TS types).
- Prefer **Server Components** for initial data (schedule, matchup detail) —
  fast first paint, SEO-friendly for shareable matchup links. Use client
  components only where interactivity needs it (ThemeToggle, WeekSelector
  interactions, the split-bar animation).
- Handle loading/error explicitly; if the backend is down, show a friendly
  message, not a crash.

### 5.5 Theming implementation

- CSS variables on `:root`; `data-theme="dark|light"` on `<html>` overriding
  a `prefers-color-scheme` default (same token pattern as the mockup). With
  Tailwind v4, wire the tokens as CSS custom properties and reference them
  from utilities/`@theme`. `ThemeToggle` sets `data-theme` + persists.
- Avoid the flash-of-wrong-theme: set the initial theme via a tiny inline
  script before hydration (read localStorage / media query).

### 5.6 Responsive & a11y

- **Mobile:** hero collapses to stacked team cards (drop the center "VS"),
  ticker → 2 cols, week selector scrolls horizontally. Test at 360px wide.
- **A11y:** legible contrast in **both** themes (verify the gold on green and
  on dark), visible keyboard focus, `alt` on logos, `prefers-reduced-motion`
  disables the bar animation, `tabular-nums` on all aligned digits.

### 5.7 Where to push vs. hold (for Fable)

- **Improve freely:** micro-interactions, the probability-gauge animation,
  card hover states, loading skeletons, empty/error states, typographic
  scale, overall polish, and even the exact layout of the detail page — make
  it feel premium.
- **Hold fixed:** the "Paymon Software" branding + no portfolio link; the
  mown-green-field concept and team-color-as-data split bar; full light+dark
  with sun/moon toggle; mobile-friendliness as a requirement; the footer
  trio (copyright + Buy Me a Beer + version).

### 5.8 Gaps / risks (Phase 5)

- **[GAP] Current-week logic:** define how the app picks the default week for
  2026 (based on today's date vs. the schedule). Before the season, default
  to Week 1.
- **[RISK] Logo availability/licensing:** ESPN CDN logos are convention for
  hobby projects but unofficial — the monogram fallback covers breakage;
  note the informal nature.
- **[GAP] No-data-yet UX:** pre-season, predictions may be sparse — design
  the "pending" state to look intentional, not broken.

---

## Phase 6: Testing, CI & Docs

Per PLANNING.md, this is a deliberate recruiter-facing investment.

- **Backend tests (pytest):**
  - Unit: feature engineering (esp. a **leakage test** — no feature uses
    data at/after kickoff), Elo update math, injury-severity scoring,
    team-name→abbr mapping, schema/serialization.
  - Model: a smoke test that training runs on a tiny fixture and produces a
    calibrated model; a test that 2026 Week-1 cold-start yields non-degenerate
    probabilities.
  - API: FastAPI `TestClient` over the endpoints with a seeded test DB
    (SQLite or a disposable Postgres) — assert the response contracts.
  - LLM: mock the Anthropic client (no real calls in tests); assert the
    fallback path (null narrative) works.
- **Frontend:** at minimum typecheck + lint in CI; component tests optional
  for v0.1.0 (add once UI stabilizes).
- **CI (GitHub Actions):** on push/PR — matrix of (a) backend: ruff + pytest
  against a Postgres service container; (b) frontend: `npm ci`, lint,
  `next build`. Keep it green as the definition of "mergeable."
- **Docs:** keep `README.md` current (setup already drafted); add a
  `backend/README.md` for pipeline/model commands; surface the backtest
  results table + calibration plot in the README once they exist (this is the
  single most persuasive artifact for recruiters).

---

## Recommended build order (dependency-aware)

1. **Phase 0** foundations (config, DB, models, Alembic, CI skeleton).
2. **Phase 1.1–1.2** seed + historical backfill → real data to model on.
3. **Phase 2** features → train → backtest → calibrate → artifact (+ the
   leakage test early).
4. **Phase 3** API over cached predictions (stub predictions first if needed
   so the frontend can start in parallel).
5. **Phase 4** narration into the batch job.
6. **Phase 1.3** 2026 recurring refresh jobs (needs the 2026 schedule +
   keys; can be built against 2025 as a dry run before 2026 data exists).
7. **Phase 5** frontend (can begin against the Phase 3 contract with mock
   data as soon as schemas are fixed — parallelizable with 3/4).
8. **Phase 6** harden tests + CI throughout, not just at the end.

**Parallelization note for Fable:** the Phase 3 response schemas are the
contract seam — freeze those early and the frontend (Phase 5) and backend
(Phases 1–4) can proceed independently. Consider a `mock` mode on the API
that returns fixture predictions so the UI is buildable before the model is
trained.

---

## Forward-looking (NOT v0.1.0 — noted so the design doesn't paint into a corner)

- **Deploy:** Vercel (frontend) + Cloud Run (FastAPI) + Cloud SQL/Supabase
  (Postgres); scheduled refresh via Cloud Scheduler → Cloud Run job. Cut
  `1.0.0` at public launch.
- **Hypothetical matchups** (any two teams) — becomes relevant near the
  playoffs; the feature builder should stay decoupled enough to score an
  arbitrary pairing later.
- **Auth** — only if per-user state (favorites, saved picks) is added. Flag
  it then; out of scope now.
- **Later products** (start/sit, rankings, trade calc, NFL passport) — keep
  the model/data layers reusable, but don't build for them yet.

## Resolved decisions (from planning)

1. **2026 schedule source:** `nfl_data_py` *probably* exposes the 2026
   schedule; **if not, fall back to ESPN's schedule endpoint or a
   web-sourced schedule** for a one-time seed of `games` (see Phase 1.3).
   Source is swappable — the `games` rows are what matter.
2. **Historical Vegas data:** ✅ Use nflverse historical
   `spread_line`/`total_line` for the *training* market feature; reserve The
   Odds API for current 2026 games (free-tier discipline).
3. **Fonts:** ✅ **Fable chooses.** Distinctive and characterful — **not**
   Arial/Calibri/Helvetica/Inter-type defaults — but still highly readable
   at a glance (see Phase 5.1).
4. **Narrative voice:** ✅ **Fun — an energetic radio play-by-play
   broadcaster:** stat-dense and detailed, delivered with excitement, while
   still bound by the "never invent stats / never change the probability"
   guardrails (see Phase 4.2).
