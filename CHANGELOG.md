# Changelog

All notable changes to Blitzcast are documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.1] — 2026-08-21

First production deploy: Railway (backend API + Postgres + weekly NFL/CFB
refresh crons) and Vercel (frontend) behind `blitzcast.app`.

### Fixed
- `data_pipeline.backfill`'s `backfill_injuries` passed pandas `NaN`
  directly into the `status` column. Mixing `NaN` and string values in the
  same batch insert made psycopg2 misinfer the column type from the `NaN`
  rows and reject every row with an actual status string.
- `backfill_cfb`'s `--end` default was still 2025, a season behind the NFL
  backfill's default; the current season silently never loaded without an
  explicit override.
- `railway.json`'s start command included a redundant `cd backend &&`
  left over from before the service's Root Directory was set, breaking
  every deploy.
- `psycopg2-binary` was missing from `requirements.txt`; Alembic imports it
  directly and failed at migration time even though the app itself runs on
  `psycopg` (v3).

### Changed
- The frontend API client now revalidates every 30 seconds
  (`next: { revalidate: 30 }`) instead of `cache: "no-store"`, and the
  matchup detail page dropped `force-dynamic` in favor of the same window.
  Predictions only change on the weekly cron refresh, so the previous
  every-request round trip to Railway bought no real freshness — it only
  cost latency, most noticeable on mobile/cellular connections.

## [1.0.0] — 2026-08-17

First public release. Model artifacts are retrained and stamped `1.0.0`
(NFL) and `cfb-1.0.0` (CFB); the app version and the model version are
tracked separately, as before.

### Added
- `GET /api/record?sport=NFL|CFB&season=2026`: current-season prediction
  accuracy graded against the market's accuracy over the identical sample
  of games, excluding reconstructed/backtest predictions. Reports
  `sufficient: false` below 10 graded games rather than a number that
  isn't meaningful yet.
- `?status=all|final|upcoming` query param on `/api/games` and
  `/api/schedule`. Unknown values fall back to `all` rather than 422ing,
  matching the frontend's existing tolerance for unknown filter values.
- `GameSummary` and `PredictionOut` gained `home_score`, `away_score`,
  `prediction_correct` (true/false, or `null` when there's nothing to
  grade: no prediction yet, an unplayed game, a tie, or an exact 0.5
  pick'em), and `market_home_prob`.
- `backend/app/jobs/backfill_predictions.py`: walk-forward backtest job
  that reconstructs historical predictions (2023-2025, both sports) from
  models trained only on strictly prior seasons, mirroring
  `ml/backtest.py`. Written under distinct `backtest-1.0.0` /
  `backtest-cfb-1.0.0` model versions so they're excluded from the live
  record and can be labeled in the UI as reconstructed. Run with
  `python -m app.jobs.backfill_predictions --sport nfl|cfb`.
- `assert_temporally_disjoint` in `ml/train.py`: raises if the training
  and calibration windows ever overlap, so a future mid-season retrain
  that widens `TRAIN_SEASONS` can't silently leak.
- Frontend: finished games show the final score, a winner-emphasized
  display, and a "Called it"/"Missed" verdict badge (color plus text, not
  color alone) on the game card and matchup page.
- `StatusFilter` component (all / completed / upcoming) on both slates;
  filter state lives in the URL and survives week and conference
  navigation.
- `RecordBanner`: model accuracy shown next to the market's at the top of
  each slate, never the model's number alone; "Not enough games yet"
  below the 10-game threshold.
- `Disagreements` component: the week's largest gaps between the model's
  win probability and the market's, framed as a curiosity worth reading,
  not a betting signal.
- `/how-it-works`: a methodology page, linked from the footer, covering
  the model's inputs, the leakage rule, the LLM boundary, and an honest
  reading of the Vegas comparison numbers.
- `opengraph-image.tsx` for matchup pages: team names plus win probability
  (or final score and verdict) on Blitzcast's turf branding, paired with
  a `twitter` summary card.
- `sitemap.ts` / `robots.ts`: bounded to the current season, cached via
  `unstable_cache` at a 1-hour revalidate so repeated crawler hits can't
  force a schedule fetch on every request.
- Matchup pages backed by a `backfill_predictions` row are labeled
  "Reconstructed from a backtest, not a live call made before kickoff."
- `LICENSE`: MIT.
- `frontend/src/app/error.tsx`: route-level error boundary. Anything the
  API client does not turn into a `NotFoundError` or `ApiUnreachableError`
  previously surfaced Next's raw "Application error" page.
- `backend/tests/test_odds.py`: pins the stored spread convention against
  the moneyline favorite. The Odds API ingestion path had no test fixture
  at all, which is why the sign bug below went unnoticed.
- Frontend tests for `fmtSpread`, `pickDefaultWeek`, and
  `pickCfbDefaultWeek` (52 tests, up from 38).
- `.env.example`: `CFBD_API_KEY` and `MODEL_VERSION_CFB`, both previously
  undocumented. Without the former every CFB job silently skips.

### Fixed
- `predict_week` no longer re-predicts a game once both scores are in, and
  the weekly prediction job's own `default_week` no longer sticks on a week
  with a permanently-unscored game (a 36-hour post-kickoff hold before that
  week is treated as done, so a cancellation can't pin the prediction job
  on a stale week forever). Unrelated to the slate UI's own week rollover,
  which stays a separate 12-hour hold.
- NFL games in a week nflverse hasn't scheduled real broadcast times for
  yet (observed for Week 18 far in advance) were getting a fake confident
  kickoff time instead of TBD: nflverse fills every game in such a week
  with one repeated placeholder `gametime` string rather than leaving it
  blank, so `kickoff_time` is now written `NULL` for any (season, week)
  where every game shares a single non-null gametime. CFB already handled
  this correctly via CFBD's explicit TBD flag.
- **A pick'em market line was being scored as a market loss instead of
  excluded.** `/api/record` skips a graded game when the model's own
  probability is exactly 0.5 (no favorite), but the market side of that
  same check evaluated `bool(None)` to `False` and counted the game as a
  market miss rather than skipping it too, biasing the record in the
  model's favor. Affects roughly 22 finished games in the current
  historical data (symmetric moneylines or a zero spread). Fixed in both
  the live and mock-mode implementations, with regression tests on each.
- **Spread sign was inverted for live odds.** The Odds API quotes betting
  convention (negative = home favored) while `games.spread_line` follows
  nflverse (positive = home favored). Both were written to the same field
  unnormalized, and `ml/features.py` prefers the live row, so
  `market_spread_home` was sign-flipped at inference on exactly the
  upcoming games users see, contradicting `market_home_prob` (derived from
  the moneylines). The frontend compounded it by assuming the book
  convention, naming the wrong favorite on every game with a spread.
  Normalized at ingestion, corrected in `fmtSpread`, and the affected rows
  were rewritten.
- `prediction_status` returned `"available"` while the frontend contract
  only recognized `"ready"`, so every completed prediction rendered in the
  pending state, hiding the reasoning panel and narration site-wide.
- `_prediction_probs` had no ordering and no scope: it full-scanned the
  predictions table on the two hottest endpoints, and with more than one
  row per game (which a model version bump creates) the slate could
  disagree with the matchup page. Now scoped to the slate and resolved to
  the newest prediction.
- `/api/predictions/{game_id}` returned 500 for a game with a home score
  but no away score.
- `data_pipeline/seed.py` matched teams on abbreviation alone, so
  re-running the documented seed step could overwrite the CFB BUF, CIN,
  HOU, or MIA rows with NFL data.
- `team_game_stats` was never re-ingested in-season (a hardcoded
  `<= 2025` in the backfill, and no step in the weekly refresh), so the
  rolling EPA and turnover form features decayed to null a few weeks into
  a season while SHAP kept labeling them. The season list is now derived
  from which seasons actually have results, and `refresh_stats` runs
  weekly.
- `refresh_weather` had no sport filter while being called by the CFB
  orchestrator, so it fetched a full FBS slate (~70 calls) per run against
  a free tier. It now defaults to NFL, commits per game so a late failure
  cannot roll back calls already paid for, and is no longer invoked by
  `refresh_week_cfb`.
- Injury refresh deleted only the games present in the incoming batch, so
  a team reporting fully healthy kept last week's injuries feeding
  `qb_out_diff` and `injury_sev_diff`. It now clears every upcoming game
  being refreshed.
- Odds could be captured after kickoff (the fetch window reached back six
  hours) and an in-play line would then be preferred over the closing
  line in training. The window now starts at the current time, and the
  feature build ignores any capture at or after kickoff.
- Poll refresh deleted a whole season before inserting, so a partial CFBD
  response wiped the weeks it did not include. Scoped to the returned
  weeks.
- `predict_week` held one transaction across the whole slate, including
  every Claude call, so a late failure discarded roughly a hundred
  computed predictions. Commits per game; the upsert was already
  idempotent.
- `ml/compute_ratings.py` ordered by `kickoff_time` alone, so CFB TBD
  kickoffs (NULL) replayed after every dated game and fired season
  regression repeatedly. Coalesced with `game_date`, matching
  `features.py`.
- Elo replay in both `features.py` and `compute_ratings.py` guarded on the
  home score but read both, so a row with one side scored would raise.

### Verified, not changed
- CFBD's regular-season "week N" poll is published *before* week N's games,
  confirming `poll_strength` carries no leakage. Checked against the live
  2025 AP polls: all six ranked teams that lost in week 1 held their week 1
  rank and fell only in week 2 (Texas #1, lost to Ohio State, #7 the next
  week). Pinned by `tests/test_cfb_polls.py`.
- `Odds` and `Weather` were typed non-nullable on the frontend while the
  backend returns every member nullable, rendering the literal string
  `null` in the stat ticker.
- A single TBD kickoff pinned the NFL default week for the rest of the
  season; a leftover TBD no longer holds a finished week open.
- CFB weeks rolled over Sunday 20:00 ET instead of Monday 00:00 ET,
  advancing users to an empty slate a few hours early.
- `FactorList` divided by zero when every SHAP value was 0, blanking all
  bars.
- Rams display: nflverse keys them `LA`, so the frontend's `LAR` lookup
  silently missed, dropping the logo and team colors. Internal keys stay
  `LA`; only rendered text shows `LAR` (Chargers remain `LAC`).

### Changed
- Narration prompt rewritten toward an ESPN / College GameDay register,
  with an explicit instruction against em dashes plus a deterministic
  sanitizer, since the prompt itself contained one and roughly 90% of
  stored narrations echoed it.
- Em dashes removed from user-visible copy: page titles, meta
  descriptions, empty states, and the mock narratives.
- Mock fixture spreads realigned to nflverse convention so each agrees
  with its own moneyline.
- `metadataBase` now reads `NEXT_PUBLIC_SITE_URL` / `VERCEL_URL` instead
  of being hardcoded to `http://localhost:3000`.
- `SECURITY.md` replaced its placeholder text with a real reporting
  policy; `frontend/README.md` replaced create-next-app boilerplate.
- Comment cleanup: `[VERIFY]` markers, Alembic and Jest scaffolding, and
  citations to planning docs that no longer exist.

### Removed
- Five unreferenced create-next-app SVGs from `frontend/public/`.

### Security
- `.gitignore` now matches `.env.*` with a `!.env.example` negation, so a
  `.env.production` written during deploy cannot be committed.
- Frontend: resolved all 18 open Dependabot alerts (11 high, 7 moderate).
  Bumped `next` 16.2.10→16.3.0 and `eslint-config-next` to match (fixes 9
  Next.js advisories — SSRF, DoS, cache confusion, middleware bypass).
  Added `overrides` pinning transitive deps to patched versions: `postcss`
  ≥8.5.23, `nanoid` ≥3.3.17, `js-yaml` ≥4.3.1, `sharp` ≥0.35.0, and a
  scoped override for `brace-expansion` ≥1.1.16 under `eslint` specifically
  (left the separate `typescript-eslint`→`brace-expansion` v5 chain alone,
  since GitHub had already auto-dismissed that advisory as not applicable).
  `npm audit` now reports 0 vulnerabilities.

### Changed
- `frontend/next.config.ts`: set `agentRules: false` to opt out of Next.js
  16.3's new auto-generated `AGENTS.md`/`CLAUDE.md` scaffolding — this repo
  already has a hand-maintained root `CLAUDE.md`.

## [0.3.0-beta] — 2026-08-09

### Changed
- Replaced `PLANNING.md`/`IMPLEMENTATION_PLAN.md` with `DECISIONS.md` — a
  concise, what/why/alternative log of significant technical decisions
  (walk-forward backtesting, difference features, calibration, batch
  predictions, anti-leakage testing, SHAP, LLM narration boundary, the CFB
  `sport`-discriminator design, narration model choice, Odds API batching,
  and the frontend/backend split), replacing the retroactive planning docs
  with an accumulating engineering record. `README.md` and `CLAUDE.md`
  now point here instead.

### Added
- `SECURITY.md` — a basic placeholder vulnerability-reporting policy
  (private GitHub security advisories), linked from `README.md`. A fuller
  policy is planned once the app has a public deployment/domain.

### Removed
- Root `VERSION` file — `frontend/package.json`'s `version` field (already
  read by the footer) is now the single source of truth; releases are
  tagged on GitHub going forward instead of tracked in a standalone file.

### Fixed
- CI: bumped `actions/checkout` (v4→v7), `actions/setup-python` (v5→v6),
  and `actions/setup-node` (v4→v6) to versions that target the Node 24
  Actions runtime, clearing the "Node.js 20 is deprecated" warnings.
  Also bumped the `frontend` job's own build/lint Node version (22→24)
  to the current Active LTS.

## [0.2.0-beta] — 2026-07-12

### Added
- College football (CFB / FBS) as a second sport, alongside NFL, in the
  same app — one Postgres DB with `sport` as a first-class discriminator,
  not a fork.
- CFBD-backed data pipeline for CFB: team/conference seeding, historical
  backfill (2021–2025), current-season schedule sync, and AP/Coaches poll
  refresh (`data_pipeline/*_cfb.py`).
- Per-sport Elo, feature engineering, XGBoost model, and calibration for
  CFB, trained and backtested independently of NFL
  (`ml/reports/backtest_cfb.md`).
- `sport=NFL|CFB` query param on `/api/teams`, `/api/schedule`,
  `/api/games`; `--sport` flag on `compute_ratings`, `train`, `backtest`,
  and `predict_week`.
- `/nfl` and `/cfb` tabs on the frontend, with sport-aware routing
  (`/[sport]`, `/[sport]/matchup/[gameId]`) and a TBD-kickoff badge for
  CFB games without a confirmed time.

### Fixed
- `ml/features.py`: leakage-safe merge/chronological ordering now
  coalesces null `kickoff_time` (CFB's TBD-kickoff games) to `game_date`,
  fixing a `merge_asof` crash and a latent Elo-replay ordering bug. No
  effect on NFL, where `kickoff_time` is never null.
- `ml/features.py`: injury-diff feature columns are now explicitly cast
  to `float`, fixing an XGBoost dtype rejection that only surfaced for
  CFB (which has no injury data source, unlike NFL).

## [0.1.0-beta] — 2026-07-09

### Added
- Initial release: NFL matchup predictor. XGBoost home-win model over
  20 leakage-safe features (Elo, rolling EPA/form, rest, injuries,
  weather, market), Platt-calibrated, walk-forward backtested against
  Vegas closing lines (`ml/reports/backtest.md`).
- FastAPI backend serving cached predictions (`/api/teams`,
  `/api/schedule`, `/api/games`, `/api/predictions/{game_id}`), with a
  weekly batch job (features → predict → SHAP → narrate → upsert).
- Claude-narrated (Haiku 4.5) broadcaster-style explanations, guardrailed
  to describe the model's output without altering or inventing it.
- Data pipeline: nflverse historical backfill, weekly odds/weather/injury
  refresh, all degrading gracefully without API keys.
- Next.js + Tailwind frontend: week slate and matchup pages, light/dark
  themes, mobile-first, with a full mock mode for keyless development.
