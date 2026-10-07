# Changelog

All notable changes to Blitzcast are documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.1.3] — 2026-10-07

The booth always names a pick. The model, its probabilities (other than the
exact-tie rule from 1.1.2, now with a moneyline step), and `MODEL_VERSION`
(`1.0.0` / `cfb-1.0.0`) are unchanged.

### Changed
- The booth narration always names the model's pick, the side the stored
  probability favors. When the rounded percentages tie (49.5 to 50.5
  percent) the template says "Our model leans X by the slimmest of margins"
  (or "by a hair"), "50% for each side", and the minimal model-only line does
  the same. The fact sheet always states the model's pick, the prompt forbids
  toss-up, coin flip, too close to call and no-clear-favorite wording for the
  model's view, `check_narration` rejects common forms of that wording (market
  wording about a line of 0, such as "the line is a pick'em", is still
  allowed) and, within one point of even, a draft that names no model pick,
  and `still_true` rejects any stored narration containing a no-pick phrase,
  so a kept "coin flip" text is replaced by the template.
- Near-even games (the home percentage rounds to 49, 50 or 51) are narrated
  from the deterministic template, which always names the pick: no Claude
  call and no kept narration for them. They count as fallback in the
  narration summary, and a line before it says how many were written from the
  template by design.
- For ordinary games, a draft that names the wrong team as "the model's
  pick", "our pick", "the model's lean/call" or "the model's pick here is X"
  is rejected, as is "no clear pick" wording; market "favored by" wording does
  not count as naming the model's pick. Some pick phrasings are still not
  read (see DECISIONS.md).
- The exact-tie break in `predict_week` now falls through the posted spread
  (positive means the home team is favored), then a plausible moneyline pair
  (the single `plausible_moneylines` rule), then the home team. Previously a
  spread of 0 or no spread went straight to home.
- Mock fixture text in `frontend/src/lib/mock.ts` no longer says "coin flip";
  no UI behavior change.

### Added
- `home_moneyline` and `away_moneyline` metadata columns on the feature
  frame, read only by the exact-tie break. `FEATURE_COLUMNS` and the model
  artifacts are unchanged.

### Fixed
- A game at 50.01 percent no longer reads "coin flip" in the booth while the
  page names a pick.

## [1.1.2] — 2026-10-03

Prediction coverage patches. The model, its probabilities (other than the
exact-tie rule below), and `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`) are
unchanged.

### Changed
- The daily prediction job now predicts every unplayed game kicking off
  within seven days (`LOOKAHEAD_DAYS`), plus the current week, so a game has
  a prediction and booth section once the game kicks off within seven days
  (or is in the current week). A TBD-kickoff game more than 36 hours past
  its game date is no longer selected or reported as a gap. Previously
  next week's games stayed "prediction pending" until the morning of its
  first game. `--week N` behaves as before.
- An exactly even (50.0000 percent) prediction is nudged by 0.0001 toward
  the betting favorite (the home team when there is no posted line) when it
  is written, so the model always picks a side and the page, the share image
  and the season record agree. Near-ties such as 50.27 versus 49.73 and all
  finished games are untouched.
- The NFL and CFB cron runs now run every step and then exit 1 when the
  prediction step failed or was skipped because the schedule sync failed.

### Added
- Per-game failure isolation in `predict_week`: one game that errors is
  rolled back and logged by exception type, the rest of the slate still
  runs, and the run prints `predictions: N ok, F failed` and exits non-zero.
- An end-of-run coverage check, and `python -m app.jobs.coverage
  [--season] [--sport nfl|cfb]` (read-only, current model version), that
  lists upcoming games with no prediction or no booth section and exits
  non-zero when any exist.

### Security
- Venue, city, conference, division, team name and mascot strings are gated
  for ad words and number words, in addition to the existing link-word and
  digit-run rules, so a hostile or vandalized feed value is treated as
  missing. The gate stops lowercase-word and number-word style injection
  only; the guarantee remains the output guardrail (`check_narration`).
- Narration drafts may not contain a vanity phone number such as
  "1-800-PICKS".
- A spaced or punctuated phone number is now caught on both sides: the gate
  rejects a feed string with more than four digits in all, and the output
  rule counts digits chained by short punctuation such as "(8 0 0) 5 5 5".

### Fixed
- `build_features` no longer crashes for CFB when the season has no played
  games.

## [1.1.1] — 2026-10-03

A hotfix for the 1.1.0 narrator. The model, its probabilities, and
`MODEL_VERSION` are unchanged.

### Fixed
- The narrator's API call no longer passes an argument the pinned SDK
  rejects. 1.1.0 sent `temperature`, which `anthropic` 1.0.0 does not
  accept, so every AI draft failed and every game fell back to the
  template. Sampling is back to the API default; the 1.1.0 note about a
  temperature of 0.8 never took effect.

### Added
- A signature-guard test that binds the narrator's call to the real SDK
  `messages.create` signature, so a mocked client can no longer hide this
  class of error.

## [1.1.0] — 2026-10-02

The "From the booth" narration is rebuilt around verified facts. The model,
its probabilities, and `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`) are
unchanged; the retrain is a later release. Claude Haiku (via
`ANTHROPIC_MODEL`) still writes the copy.

### Added
- A pre-game fact sheet (`app/services/fact_sheet.py`) that the narrator
  works from instead of raw SHAP values: each team's record, last result,
  streak, and recent scoring, the venue and kickoff window, the betting
  line written out in words, NFL injury-report names (Out and Doubtful),
  CFB AP poll ranks and week-over-week movement, and the model's top
  factors in plain English. Every fact is built from data strictly before
  kickoff.
- `check_narration` in `app/services/narrate.py`, the guardrail every draft
  must pass. It verifies the model's pick and each percentage per team, the
  market favorite and the line wording, every capitalized name against the
  fact sheet, spelled-out numbers, scores, records, streaks and ranks, and
  CFB injury talk.
- A deterministic fallback narration (`app/services/fallback_narration.py`),
  built from the same fact sheet and held to the same check, so every game
  with a prediction gets a booth section even when no AI draft survives.
- `Team.mascot` (migration `c3f1a9d27e48`, additive), filled by the next
  `seed_cfb` run. The migration is applied automatically on API deploy
  (`railway.json` runs `alembic upgrade head` on boot), but CFB mascots only
  appear after `seed_cfb` is run once following it. Deploy order: merge
  outside the 09:00 to 10:00 UTC cron window and confirm the API deploy
  (which applies the migration) succeeded before the crons read
  `Team.mascot`, then `seed_cfb`, then the `predict_week` re-runs.
- `python -m app.jobs.narration_eval --sport nfl --week N` measures the
  guardrail pass rate, mean attempts and fallback coverage without writing
  anything. `--stored` re-checks saved narrations for free; fresh
  generation spends Anthropic tokens and requires `--spend-tokens`.
- A per-run narration summary from `predict_week`:
  `narration: N written, K kept, F fallback, L minimal, J none`, with a
  `WARNING:` line when any game ended up with none.

### Changed
- The narrator voice: a pregame-show structure at whip-around pace (stakes
  first, then the model's pick and number, then one or two reasons from the
  sheet). No real show names. Temperature is 0.8.
- A rejected draft's reason is now fed back to the model on the retry (up
  to 3 attempts) instead of a blind second try.
- The `predict_week` chain: a fresh AI draft, else the stored narration
  only if it is still exactly true today, else the deterministic template
  from the fact sheet, else a minimal model-only line (both teams'
  abbreviations and percentages) if even the fact sheet cannot be built.

### Fixed
- Narrations that misread the stored spread sign. A positive home spread
  means the home team is favored, and the fact sheet now states the
  favorite and the line in words so there is nothing to misread.
- Invented player names and venues, and "last five games" talk when the
  window actually spans last season (the sheet flags those factors).
- Games with no booth section. A production check found 5 of 22
  model-vs-market disagreement games had none (0 of about 430 agreeing
  games); the fallback closes that gap.
- A failed narration can no longer block a prediction: fact-sheet or
  narration errors are caught per game and the prediction is still written.
- A failed re-narration can no longer erase a still-valid one: the stored
  narration is kept when it is still exactly true today (every percentage is
  today's number, every other number is on today's fact sheet, weather talk
  is backed by today's weather), and replaced otherwise.
- A CFB rematch is never called a "postseason" meeting: CFBD numbers
  Army-Navy as regular-season week 16, so every CFB meeting reads
  "Week N of season".
- `seed_cfb` cuts a mascot to the 40-character column, so one long value
  cannot roll back the whole seed.

### Security
- Untrusted feed text is cleaned before it reaches the narration: team,
  mascot, conference, venue, city and injury-report strings become one
  plain line (no newlines, control characters or symbols beyond
  `. ' & ( ) -`), so a vandalized value cannot forge fact-sheet rows. The
  prompt marks the sheet as data, never instructions. Published copy may
  not contain a link, domain, handle, slash, long digit run or non-Latin-1
  letter; numbers are checked only against trusted fields, never venue or
  player text; rejections are logged as fixed categories; and the Anthropic
  client times out after 30 seconds with one retry.
- A venue, city, conference or division that does not read like a name (a
  link word, 3 or more digits in a row, or a lowercase word other than "of",
  "the", "de" and similar) is treated as missing, so the template can never
  publish an ad posing as a stadium. Published copy is checked in its NFKC
  form and may not contain "dot com" links, "hxxp", or a phone-like digit
  run; scores and streaks inside team, mascot or conference text back no
  claim; and the minimal line only uses abbreviations that look like one.

## [1.0.14] — 2026-10-01

### Security
- Bumped `next` (16.3.5 to 16.3.6), which fixes GHSA-vcvr-r3jv-pc5j, a
  remote code execution in `next/og` `ImageResponse`. This app uses
  `next/og` for its Open Graph images.
- Bumped the transitive `brace-expansion` (1.1.18 to 1.1.21 and 5.0.9 to
  5.0.12), which carry upstream security fixes (lockfile only).
- Applied directly rather than by merging the Dependabot PRs, to avoid
  `dependabot[bot]` appearing in the contributor graph.

## [1.0.13] — 2026-10-01

### Fixed
- CFB predictions now use 2026 game stats. The daily CFB cron never loaded
  current-season team-game PPA, so every CFB team's "EPA, last 5 games" was
  last season's data: one 2025 game at week 5 and nothing from week 6 on.

### Added
- `data_pipeline/refresh_stats_cfb.py` (`python -m
  data_pipeline.refresh_stats_cfb [--season 2026]`), run by
  `refresh_week_cfb` right after the schedule sync and before odds. It
  re-ingests the season's team-game PPA from CollegeFootballData through
  the existing idempotent `backfill_team_game_stats`, at one CFBD call a
  day. It skips with a message until the season has a final game, a
  missing `CFBD_API_KEY` prints a `WARNING:` (exit 0), and a CFBD request
  failure prints the error and exits 1 (the key travels only in a request
  header, so the message cannot contain it).

## [1.0.12] — 2026-10-01

### Fixed
- Weather: `refresh_weather` gains `--backfill-days N`, which also fetches
  past games that have no weather row, so one missed daily run no longer
  leaves a game without weather for good. It now exits 1 when every
  attempted call failed (it stays 0 for partial failures), and a missing
  `VISUAL_CROSSING_API_KEY` prints a `WARNING:` instead of skipping
  quietly (still exit 0). The orchestrators ignore step exit codes by
  design, so a total failure shows in the cron logs only.
- The CFB loader now records `is_neutral_site` and, for venues with no
  Stadium match, `venue_name`, so weather can geocode neutral-site games.
- Moneyline sentinels such as `HOW -100000 / RUTG -100000` are no longer
  stored or shown. One rule, `real_moneyline` and `plausible_moneylines`
  in `backend/app/market.py` (a 100000 sentinel, and an implied-probability
  sum outside 0.95 to 1.25), is shared by the CFBD loader, the feature
  builder, the Odds API consensus (an implausible book no longer claims
  the h2h slot), and the API, which hides the moneylines as a pair. Checked
  against 408 real production pairs: it rejects exactly the 25 placeholder
  pairs.
- Games with no market line no longer claim a Vegas lean or skew to the
  home team. All 8 such 2026 games were getting 75 to 86 percent home, and
  the explanation said "Vegas favors away". Their market features are now
  imputed from Elo, flagged by `has_market_line` and `has_market_spread`,
  and a derived spread is never shown or narrated as a posted Vegas
  spread. `top_factors` gains `market_available` and `spread_available`,
  and the backtest's "Vegas" baseline excludes imputed rows. The flags are
  not model inputs yet, so the committed 1.0 models are unchanged.
- The completion invariant now holds in `features._team_form`, `home_win`,
  `refresh_stats`, and the NFL `games_loader` status: a game counts as
  played only when both scores exist.
- Visible empty-value placeholders are now `N/A` (stat ticker, spread) and
  `TBD` (pending win probability, OG card) instead of em dashes.

### Changed
- `refresh_week` and `refresh_week_cfb` now pass `--backfill-days 3` to the
  weather step.

## [1.0.11] — 2026-09-14

### Fixed
- `predict_week`'s unplayed-game selection now also excludes any game whose
  kickoff has already passed, not just games with a recorded score.
  Previously a game already underway, or one whose final score simply
  hadn't landed from the data source yet, still had both scores NULL and
  would get silently re-predicted by the next daily cron: identical
  pre-game inputs, but `predicted_at` restamped to a time after kickoff. A
  NULL (still-TBD) kickoff stays eligible regardless of the current time.

## [1.0.10] — 2026-09-14

### Added
- `diagrams/`: ten hand-maintained Mermaid architecture diagrams (C4
  context and container, the Postgres ER diagram, the prediction request
  and daily refresh sequences, the LLM narration guardrail boundary, the
  ML train/validate/serve pipeline, the game lifecycle, and deployment and
  security), indexed in `diagrams/README.md` with a re-check table, and
  linked from the READMEs and CLAUDE.md.
- `/.well-known/security.txt` (RFC 9116) pointing researchers at private
  vulnerability reporting. Expires 2027-09-14; renewal is noted in
  SECURITY.md and CLAUDE.md.
- DECISIONS.md entries for pinning Python dependencies and for
  hand-maintained diagrams.

### Changed
- CI now runs the frontend Jest suite on every push and pull request.
  Previously only lint and build ran, despite the README saying both test
  suites were covered.
- `backend/requirements.txt` and `requirements-dev.txt` pin every
  top-level dependency to the versions production was running. Unpinned,
  any rebuild that missed Railway's cache could silently change the
  xgboost/scikit-learn versions the committed model files were saved with.
- `next` and `eslint-config-next` 16.3.3 → 16.3.5 (patch releases; no
  open advisories).

### Fixed
- Stale documentation: the README's hardcoded version (1.0.3) is now a
  release badge; SECURITY.md's supported-versions table names "Latest
  release" instead of a number; the crons are described as daily, not
  weekly; hardcoded test counts removed; CLAUDE.md's routes,
  `MODEL_VERSION`, and committed-artifact notes corrected; the
  `backfill_cfb` usage docstring now matches its `--end 2026` default.
- `railway-cfb-cron.json`'s `$schema` URL was missing its `https://`.
- The portfolio embed is described generically in DECISIONS.md,
  CHANGELOG.md, and `next.config.ts` comments; the CSP value itself is
  unchanged.

## [1.0.9] — 2026-09-09

### Fixed
- The 1.0.8 fix (disabling prefetch on the week selector) wasn't
  sufficient on its own — verified live it was still reproducible.
  Every other bulk-rendered link list had the same problem: GameCard
  (the dominant contributor, 10-16+ per slate page), StatusFilter,
  FilterChips, and Disagreements. Disabled prefetch on all of them, plus
  Header's sport toggle (renders on every page). Re-verified live with
  the same reproduction steps against the deployed fix.

## [1.0.8] — 2026-09-09

### Fixed
- Root-caused and fixed the intermittent 503s first noticed on the week
  slate: Next.js prefetches every visible link by default, and the week
  selector renders every week (up to 18) at once, firing a burst of
  near-simultaneous requests that tripped Vercel's automatic DDoS
  mitigation. Reproduced live, confirmed via Vercel's Firewall dashboard
  it wasn't the backend (Railway showed 0% error rate throughout).
  Disabled prefetch on the week-selector links.

## [1.0.7] — 2026-09-09

### Added
- CFB's daily weekly-refresh cron now fetches real kickoff weather
  (temp/wind/precipitation) for outdoor games, same as NFL. CFB games
  already carry real stadium coordinates from CFBD; the weather script
  itself worked all along, it just was never wired into the CFB
  orchestrator. Checked against the Visual Crossing free tier's 1000
  records/day. Display-only for now — the current CFB model was trained
  before this existed, so it can't yet use it in predictions.

## [1.0.6] — 2026-09-08

### Security
- Bumped `next` (16.3.0 → 16.3.3, fixes 2 critical unauthenticated RCE
  advisories), `js-yaml` (4.3.1 → 4.3.2, fixes a high-severity CPU DoS),
  and `sharp` (0.35.0 → 0.35.4, fixes 2 high-severity libheif
  vulnerabilities). Applied manually rather than merging Dependabot's own
  PRs, to avoid `dependabot[bot]` appearing in the contributor graph.

## [1.0.5] — 2026-09-08

### Fixed
- Follow-up to the 1.0.4 narration attribution fix: found live in the very
  prediction it targeted, a narrative could correctly call the model's own
  pick "the favorite" while separately claiming "Vegas has X favored" for
  a team the raw spread doesn't actually favor. Added a second guardrail
  scoped to sentences that reference the market specifically.

## [1.0.4] — 2026-09-08

### Fixed
- Neutral-site NFL games (international games, ~8 per season) were
  silently losing weather and venue data: the schedule loader only ever
  derived a game's stadium from its home team's normal venue, so any
  neutral-site row got no venue at all. Now captures the real venue name
  from nflverse and fetches weather by venue-name geocoding. The matchup
  page shows the real venue (e.g. "Melbourne Cricket Ground") with a
  "Neutral site" badge instead of a blank venue block.
- A CFB Week 2 matchup's SHAP factor list and narration stated the
  betting market favored the wrong team for a near-toss-up spread — a
  real SHAP-local-attribution quirk on tree ensembles, not stale or
  corrupted data. Market-derived factors now use the raw market value to
  decide direction instead of the model's local SHAP sign.
- Narration could correctly cite the model's win probability while naming
  the *wrong team* as the favorite (found in 3 of 99 CFB Week 1 games).
  Added a guardrail checking favorite/underdog attribution, not just
  percentage magnitude.
- CFBD's `-100000` "no real price quoted" sentinel was being stored and
  used as a genuine moneyline, corrupting the market win-probability
  feature toward 50/50 for real blowouts (12 CFB Week 1/2 games affected).
  Now filtered at ingestion and defensively in the feature itself.

### Investigated, not a bug
- An NFL Week 1 game displaying as kicking off on a Wednesday was flagged
  during review; confirmed the stored date and kickoff time agree with
  each other (a real Wednesday season-opener slot), not a timezone or
  off-by-one bug.

## [1.0.3] — 2026-08-27

### Fixed
- Added a site-wide default `opengraph-image`. Only matchup pages had a
  dedicated share-card image; the homepage and every other route had no
  `og:image` at all, so link previews on LinkedIn and Discord fell back to
  scraping the page for any image they could find (a team logo from a game
  card) or showed no image at all. The new default renders the same
  turf-and-wordmark card used as the matchup page's own fallback.

## [1.0.2] — 2026-08-26

### Security
- Added a `Content-Security-Policy: frame-ancestors` header scoping which
  sites may embed blitzcast.app in an iframe to itself and the maintainer's
  portfolio site, closing a previously-unrestricted clickjacking gap.

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
