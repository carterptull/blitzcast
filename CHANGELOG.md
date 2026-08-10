# Changelog

All notable changes to Blitzcast are documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

### Security
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
