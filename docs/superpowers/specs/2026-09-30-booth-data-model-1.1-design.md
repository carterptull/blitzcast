# Booth narrator, data correctness, and model 1.1: design

**Date:** 2026-09-30 · **Starting release:** v1.0.11 · **Status:** approved for implementation

This spec comes out of a review of the 2026 season's first month: all 454 live predictions
pulled from the production API, 50 "From the booth" narrations read by hand against stored
odds, polls, scores and factors, and a read-only audit of the narration, weather, odds, and
feature code. It is implemented by four plans, one PR and one release each:

| Plan | Release | Branch |
|---|---|---|
| [P1 Data correctness](../plans/2026-09-30-p1-data-correctness.md) | v1.0.12 | `ct/fix/data-correctness` |
| [P2 CFB in-season stats](../plans/2026-09-30-p2-cfb-inseason-stats.md) | v1.0.13 | `ct/feat/cfb-inseason-stats` |
| [P3 Booth narrator](../plans/2026-09-30-p3-booth-narrator.md) | v1.1.0 | `ct/feat/booth-narrator` |
| [P4 Model 1.1](../plans/2026-09-30-p4-model-1.1.md) | v1.2.0, models `1.1.0` / `cfb-1.1.0` | `ct/feat/model-1.1` |

Order: P1 → P2 → P3 → P4. P1 and P2 are independent of each other. P3 needs P1's
`has_market_line`. P4 needs P1 (imputation, completion fix, CFB neutral sites) and P2 (CFB
2026 stats at inference) and lands after P3 because both touch `predict_week.py`.

## Findings

### F1. The narration states checkable facts wrong
- **Spread sign.** Storage is nflverse convention (positive = home favored). The narrator
  receives `Vegas spread (home): 1.5` with no convention stated and reads it as sportsbook
  convention. OSU @ TEX (`cfb_401856682`, TEX -1.5) was narrated as "Ohio State getting the
  nod by a point and a half." 28 to 57 narrations (depending on idiom breadth) say the
  favorite is "getting" points.
- **Self-contradictory factor lines.** Market factors show the SHAP sign as `value` but the
  raw-value `direction`, e.g. `Vegas point spread: -0.122 (favors home)`.
- **No-line games.** `explain.py` turns a NaN line into "favors away", so all 8 no-line
  games claim "Vegas likes" a team. The model also gives the home team 75 to 86 percent in all
  8 regardless of matchup: XGBoost routes a missing market value down the branch it learned
  from training rows with no line, which were mostly FCS-at-FBS mismatches.
- **Guardrail gaps.** `_FAVORITE_RE` only matches `favorite|favored|the edge|an edge`
  ("the nod", "getting", "laying" pass unchecked). `_PCT_RE` only matches digits (19% of
  narrations spell percentages out). Mascots are invisible to team matching. Nothing checks
  proper nouns outside the payload.
- **Hallucinated context.** 4 narrations name QBs never supplied (Rodgers on the Packers,
  Mahomes x3). Venue and kickoff are never supplied: a neutral-site morning game was narrated
  as "down in Washington... tonight", the Chargers as "San Diego", GB @ NYJ as "an NFC
  matchup in the AFC East". The `week_number` factor becomes "this late in the season" in
  week 1.
- **Stale "form".** Rolling windows span seasons by design (`features.py:8-11`), so "over
  their last five games" in September describes 2025. CFB is worse (F3).
- **Style.** One template dominates: probability first, "Vegas and the betting market both
  agree" (204 of 449), "their last five games" (51%), "folks" (18%), "it's not even close"
  (14%). 0 narrations mention a record, a last result, or a streak, though all are derivable.
- **Persona.** The system prompt names real shows ("ESPN College GameDay or NFL Primetime")
  and only forbids inventing *stats*, which invites pulling names and storylines from
  training memory.

### F2. CFB weather missing for every week but one
- 2026 CFB: week 2 has 85 of 86 games; weeks 1, 3, 4, 5 have 0. Every CFB weather row was
  captured on 2026-09-09 (the one manual run). NFL is captured daily.
- Most likely cause: `VISUAL_CROSSING_API_KEY` is not set on the Railway **cfb-cron** service
  (env vars are per service). The script prints a skip line and exits 0
  (`refresh_weather.py:60-62`), so `run_step` reports success. **Ops check, not code.**
- Structural: the job selects only `kickoff_time >= now` (`refresh_weather.py:71-73`), so a
  game missed before kickoff never gets weather. NFL has 15 finished games missing weather
  the same way. Visual Crossing's Timeline API serves historical days; this is a code gap,
  not an API limit.
- CFB loader never sets `is_neutral_site` or `venue_name` (`cfb_games_loader.py:87`), so a
  CFB venue that doesn't match a Stadium row (e.g. Aviva Stadium) gets neither weather nor a
  neutral-site flag.

### F3. CFB model runs on last season's stats
- `refresh_week_cfb.py` has no stats step: **zero** CFB 2026 rows in `team_game_stats`. At
  week 5 each team's "EPA, last 5 games" is one 2025 game; from week 6 on it is NaN. This
  is a prediction bug, not just a narration bug.

### F4. Moneyline sentinels reach the UI
- `-100000` is a "no real price" sentinel. `cfbd.py` and `features.py` filter it; the Odds
  API loader (`refresh_odds.py:44-45`) takes the first bookmaker's h2h raw. 24 CFB odds rows
  carry it; Howard @ Rutgers shows `HOW -100000 / RUTG -100000`.

### F5. Smaller correctness items
- `features.py:248` (`_team_form`) and `:470` (`home_win`) decide "played" from
  `home_score` alone, violating the completion invariant. `refresh_stats.py`'s played-count
  does the same.
- Visitor-visible literal em dashes as empty-value placeholders: `StatTicker.tsx:36,53,54`,
  `MatchupHero.tsx:64`, `format.ts:63`.
- `predict_week.py:156` stamps rows with `settings.model_version_for(sport)` (env var), not
  the loaded artifact's own `model_version`, so a stale Railway env var would mislabel a new
  model's rows.

### F6. In-season results reach the model only indirectly
Elo keeps 75% (NFL) / 50% (CFB) of last season's rating gap; rolling windows cross the
season boundary; there are no season-to-date features. The market dominates SHAP.

## Decisions (user-approved 2026-09-30)

1. **Player names:** only NFL injury-report players listed Out or Doubtful for that game,
   verified by exact match. No player names for CFB (no injury data).
2. **Voice:** GameDay structure (lead with stakes and storyline, back it with model and
   market numbers) at RedZone pace (short, present-tense, energy scaled to the matchup).
   Same voice for NFL and CFB. No real show or network names in the prompt.
3. **CFB mascots:** add `Team.mascot` (Alembic migration), filled from CFBD on reseed, so
   narrations can say "the Buckeyes" and the guardrails understand mascots.
4. **Regeneration:** only games that have not kicked off when the new narrator ships. Past
   narrations stay as written.
5. **Releases:** one per PR (table above).
6. **Retrain gate (per sport):** model 1.1 ships for a sport only if its pooled walk-forward
   backtest Brier **and** log loss are both less than or equal to the 1.0 baseline re-run on
   the same code and data. A sport that fails keeps its 1.0 model and version until the
   offseason. Training windows stay `TRAIN_SEASONS = [2022, 2023, 2024]`,
   `CALIB_SEASON = 2025`, so the backtest isolates the feature change.
7. **No-line games:** impute the market features from Elo (`(elo_home - elo_away + hfa) / 25`
   points) with a `has_market_line` flag; never show or narrate an imputed line as a market.
8. **Empty-value placeholder copy:** `N/A` in the stat ticker and spread, `TBD` for a
   not-yet-predicted win probability.

## Global constraints (every task in every plan)

- **No em or en dashes in visitor-visible text** (UI strings, narration, security.txt):
  check literal `—`/`–` **and** `&mdash;`/`&ndash;`. Code comments are exempt.
- **Branding:** "Paymon" / "Paymon Software" only. Never the maintainer's real name.
- **Leakage rule:** every feature for game G uses only data from strictly before G's
  kickoff. Fact-sheet facts for narration obey the same rule.
- **Completion invariant:** never key "is this game over" off `Game.status`; always
  `home_score is not None and away_score is not None` (pandas: both `.notna()`).
- **LLM boundary:** Claude narrates model output only; it never predicts or alters a
  probability. Every checkable fact it states (favorite, market favorite, numbers, names)
  must be verifiable against what it was handed.
- **Market-factor direction** comes from the raw feature value, never the SHAP sign
  (`_MARKET_GROUND_TRUTH`).
- **Keys degrade gracefully:** a job missing its API key prints a clear `WARNING:` line and
  exits 0. A job whose every attempted external call failed exits 1.
- **Odds API budget:** 500 req/month; no new Odds API calls anywhere in this work.
- **Python:** SQLAlchemy 2.x typed `Mapped` style, ruff-clean, deps pinned (`==`). Schema
  changes via Alembic only. Comments minimal, clean, simple.
- **Committed models:** retrain only under the pinned xgboost/scikit-learn; commit new
  `.joblib` artifacts via `.gitignore` whitelist entries; keep the 1.0 artifacts committed
  for rollback.
- **Adding an API field** touches all five contract files in one change (CLAUDE.md). None of
  these plans add an API field; if an implementer finds they need one, stop and ask.
- **Diagrams:** a change to an area in `diagrams/README.md`'s re-check table updates that
  diagram in the same PR. **Every** release bumps **every** diagram footer to the new
  version (`_Last updated: <date> · reflects v<version>_`).
- **Releases:** bump with `npm version <x.y.z> --no-git-tag-version` in `frontend/` (updates
  `package.json` and `package-lock.json`), add a CHANGELOG section, add DECISIONS entries
  for non-obvious choices. The maintainer tags the GitHub release after merge.
- **Production writes:** `backend/.env`'s `DATABASE_URL` is the live Railway Postgres.
  Migrations, backfills, re-predictions, and any paid API run (Anthropic, Visual Crossing,
  CFBD) against it require the maintainer's explicit go-ahead **at that step**. Read-only
  queries are fine.
- **Git/GitHub authorship:** every commit, push, PR, and comment is authored solely by the
  maintainer's own git identity (`git config user.name` / `user.email`, unchanged). Never add
  `Co-Authored-By:` trailers, "Generated with Claude Code" lines, or any AI attribution to
  commit messages, PR titles/bodies, or comments, even if a tool or harness default asks
  for them. Never pass `--author` or alter git config.
- **Commands** (from `backend/`): `.venv\Scripts\python -m pytest`,
  `.venv\Scripts\python -m ruff check .`. Frontend (from `frontend/`): `npm run lint`,
  `npm test`, `npm run build`.
