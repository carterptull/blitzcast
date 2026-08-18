# Finished games, prediction record, and launch extras

Design spec. Target release: **Blitzcast v1.0.0**, model `1.0.0` / `cfb-1.0.0`
(no version bump; this ships under the existing v1.0.0 banner).

Status: approved for implementation planning.

---

## 1. Why

Today a completed game is visually identical to an upcoming one. Scores and
`Game.status` live in the database but are never exposed by the API and never
rendered. On the first Sunday of the 2026 season, a finished game will still
show a pre-game win probability with no score and no result. That is the most
visible flaw in the product the moment the season starts.

The audience is football fans who want a matchup call and the reasoning behind
it. For them, "was it right?" is the question that makes the rest credible.

## 2. Scope

In scope:

1. Final scores and a correct/incorrect verdict, on the slate and the matchup page.
2. A completed / upcoming / all filter, for both NFL and CFB.
3. A current-season prediction record, shown against the market baseline.
4. Backfilled walk-forward predictions so the above has content before September.
5. Prediction-integrity fixes that the above depends on.
6. OG share images per matchup.
7. A "model vs market" disagreement surface.
8. A methodology page.
9. `sitemap.ts` and `robots.ts`.

Explicitly **not** in scope:

- Mid-season retraining. See §4.
- Live / in-progress game states. No loader ever writes an `in_progress`
  status, so there is no data to render.
- User accounts, favorites, notifications.
- Browsing seasons before 2023, or any season selector UI.
- CFB postseason. See §16.

## 2.1 Build order

Dependencies are real here; this order avoids rework.

1. **Prediction integrity** (§7.1). Everything downstream displays timestamps
   that must mean "before kickoff". Do this first or the feature is built on
   sand.
2. **API contract** (§6.1, §6.2) plus mock parity. Unblocks all frontend work.
3. **Backfill** (§7.3). Produces the data needed to see and test any of the UI
   before September. Until this runs, zero games have both a score and a
   prediction.
4. **Finished-game UI** (§8). First visible result.
5. **Status filter** (§6.3, §9) and **record** (§6.4, §10). Independent of each
   other; either order.
6. **Extras**: OG images (§11), disagreements (§12), methodology (§13),
   sitemap/robots (§14). All independent, parallelizable.
7. **Temporal-disjointness guard** (§7.4). Independent; can land any time.

Steps 1-4 are a coherent first milestone worth reviewing before continuing.

## 3. Decisions already made

| Question | Decision | Rationale |
|---|---|---|
| What counts as "correct"? | Straight up: the team given >50% won | Matches how the site already talks about win probability. Not spread-relative, which would undercut the "not betting advice" framing. |
| Record scope | Current season only | Past results are already known; a record over them measures nothing about current performance. |
| Show market baseline? | Yes | A bare accuracy figure reads as an unearned brag. The model trails the market by ~3 points and the README says so. |
| Backfill source | Walk-forward backtest | Each backtest prediction was trained only on prior seasons, so the record is honest. Using the current model would be in-sample and would overstate performance. |
| Retraining | In-season adaptation only; retrain at season end | Elo and rolling form already carry current-season results into every prediction. See §4. |

## 4. What already adapts in-season (do not "fix" this)

`build_features` recomputes everything from scratch on every call, over full
history. `_load_frames` (`backend/ml/features.py:115-196`) loads **all** games
for the sport with no season filter; the `seasons` argument is applied as a row
filter at the very end (`features.py:467-468`), after the Elo replay and rolling
form have already run.

Consequently these already incorporate current-season results with no retrain:

- **Elo** (`features.py:212-231`): a chronological replay. For each game it
  calls `book.pre_game(...)`, then records the result only if both scores are
  present. A week 8 game's Elo reflects every 2026 game played before it.
- **Rolling form** (`features.py:234-276`): last-5 EPA/margin/win%, last-3
  turnover differential, joined with
  `merge_asof(direction="backward", allow_exact_matches=False)`
  (`features.py:279-294`). Windows are not reset at the season boundary.
- Rest/bye, injuries, weather, market lines, polls.

Frozen until a retrain: **only** the XGBoost weights (`TRAIN_SEASONS =
[2022, 2023, 2024]`, `ml/train.py:32`) and the Platt calibrator (`CALIB_SEASON
= 2025`, `train.py:33`).

**Why we are not retraining mid-season.** Early-season features are the weakest
they will ever be: Elo is freshly regressed toward the mean (NFL 25%, CFB 50%,
`ml/elo.py:23,38-41`) and rolling windows are seeded by prior-season games. A
Platt calibrator fit on weeks 1-6 encodes "these features are noisy" and would
leave the model systematically **under-confident** later in the season. The
calibrator is `LogisticRegression(C=1e6)` (`ml/calibration.py:7-23`), i.e.
essentially unregularized, so a small noisy sample has no shrinkage safety net.
Separately, `ml/backtest.py` is season-granular
(`backtest.py:119-127`) and therefore cannot validate whether mid-season
retraining helps.

**Required guard.** No test asserts that training rows and prediction targets
are temporally disjoint. Someone could set `TRAIN_SEASONS` to include 2026,
predict 2026 week 10, and the entire suite would pass green. This spec requires
adding that guard and its test (§7.4) so a future retrain cannot silently leak.

The record feature built here is the instrument that should trigger any future
retrain decision: it reports live 2026 accuracy against the market.

## 5. Data model

No migration required. `Game.home_score`, `Game.away_score`, and `Game.status`
already exist (`backend/app/models.py:82-84`).

**Completion invariant.** Treat a game as final when
`home_score IS NOT NULL AND away_score IS NOT NULL`. Do **not** key off
`Game.status`:

- It is derived and recomputed on every upsert, not authoritative.
- It has no index and no CHECK constraint (`alembic/versions/afd772fc0bff_initial_schema.py:57`).
- NFL sets it to `"final"` based on `home_score` alone
  (`data_pipeline/games_loader.py:71`), so it can read final with a null away
  score, which `ml/features.py:227` already guards against.
- Mock mode hardcodes `"scheduled"` for every game (`app/mock_data.py:266`).

The rest of the codebase already trusts the score-based invariant
(`predict_week.py:31`, `refresh_stats.py:33`, `services/predictions.py:180-181`,
`ml/compute_ratings.py:38`, `ml/features.py:237,460`). Stay consistent.

Add an index on `(sport, season, week)` only if the filter measurably slows the
slate; current indexes are per-column (`models.py:70-74`). Measure before adding.

## 6. API contract

### 6.1 New fields

`GameSummary` (`backend/app/schemas.py:30-40`), built in `_game_summary`
(`services/predictions.py:116-127`):

```python
home_score: int | None
away_score: int | None
prediction_correct: bool | None
```

`PredictionOut` (`schemas.py:90-107`), built in `get_prediction_detail`
(`services/predictions.py:266-303`): the same three fields. Note `PredictionOut`
carries no game-level `status` today; the three fields above are sufficient and
a `status` field is not required.

`_game_summary` already receives the `Game` and the `home_win_prob`, so the
verdict is computable in place with no extra query.

### 6.2 Verdict rule

```
prediction_correct =
  None   if home_win_prob is None            (no prediction)
  None   if home_score == away_score          (tie)
  None   if home_win_prob == 0.5              (no pick)
  True   if (home_win_prob > 0.5) == (home_score > away_score)
  False  otherwise
```

All three null cases are real: NFL ties happen, `predict_week` skips games that
already have scores (so a game finished before its first prediction ran will
have none), and an exact 0.500 is possible.

### 6.3 Status filter

Add an optional `status` query param to `/api/games` (`routers/games.py:19-25`)
and `/api/schedule` (`routers/schedule.py:19-25`), validated as a
`Literal["all", "final", "upcoming"]`, defaulting to `"all"`.

Thread through `_season_games` (`services/predictions.py:130-141`), `get_games`
(`:160-164`), and `get_schedule` (`:144-157`).

`app/mock_data.get_games` / `get_schedule` (`mock_data.py:272-290`) **must**
honor the same param or mock mode silently diverges from the real contract.
This repo has already been bitten three times by frontend/backend contract
drift; treat mock parity as part of the change, not a follow-up.

### 6.4 Record endpoint

New `GET /api/record?sport=NFL|CFB&season=2026`:

```json
{
  "sport": "NFL",
  "season": 2026,
  "correct": 11,
  "total": 16,
  "market_correct": 12,
  "sufficient": true
}
```

Rules:

- Counts only games where `prediction_correct` is non-null, in the requested
  season, for the requested sport.
- Excludes backfilled predictions (§7.3): filter by model version.
- `market_correct` counts the same games where the de-vigged market favorite
  won, so the two numbers are always over an identical sample. Derive the
  market favorite from the moneyline when present, falling back to the spread,
  mirroring `market_home_prob` (`ml/features.py:92-100`). Games with no market
  data are excluded from **both** counts.
- `sufficient` is false below a threshold (recommend 10 games). The UI must
  render an explicit "not enough games yet" state rather than `0/0` or a wild
  early percentage.

Omitting `sport` returns combined totals across both sports. The frontend must
not sum two calls itself: the market-baseline sample has to be computed over the
same filtered game set, and summing client-side would silently drift if the
exclusion rules ever differ per sport.

## 7. Backend changes

### 7.1 Prediction integrity (required, do first)

The feature's premise is "here is what we called before kickoff." Today that is
not preserved.

`refresh_week.py:29-38` runs schedule sync (which writes final scores) **before**
the prediction batch. `default_week` (`predict_week.py:25-35`) picks the earliest
week containing any game with `home_score IS NULL`, and `main` then predicts
**every** game in that week (`predict_week.py:119`), including finished ones.
`upsert_prediction` (`predict_week.py:38-52`) overwrites `home_win_prob`,
`shap_top_features`, `llm_narrative`, and `predicted_at` in place. So a Monday
run re-stamps Thursday's finished game with a post-result `predicted_at`.

The probability itself stays honest, because features are leakage-safe by
construction and re-running produces the same number. What is destroyed is the
audit trail, which is exactly what this feature displays.

Required:

1. **Skip already-final games.** In `predict_week.main`, filter `target` to rows
   without both scores. Print a count of skipped games.
2. **Unstick `default_week`.** It currently returns the earliest week with any
   unscored game forever if a game is cancelled or a CFB row never resolves.
   Prefer a kickoff-based notion of "current week", or bound the lookback.
   Document the chosen rule.
3. Both need tests.

### 7.2 Do not re-narrate finished games

Follows from 7.1: skipping final games also avoids spending Claude calls
re-narrating completed matchups.

### 7.3 Backfill walk-forward predictions

Goal: give the finished-game UI real content before the season starts, and make
it testable now. There are currently **zero** games with both a score and a
prediction.

Write a new job, `backend/app/jobs/backfill_predictions.py`:

- Reuse `ml/backtest.py`'s walk-forward loop (`backtest.py:119-127`): for each
  holdout season, train only on strictly prior seasons and calibrate on the
  latest completed prior season. Do **not** use the shipped model; it trained on
  2022-2025 and its "record" on those seasons would be in-sample.
- Persist one `Prediction` row per game with a **distinct model version**, e.g.
  `backtest-1.0.0` / `backtest-cfb-1.0.0`. This makes them queryable, keeps them
  out of the live record (§6.4), and lets the UI label them.
- Set `predicted_at` to a pre-kickoff timestamp for that game, not `now()`, so
  ordering in `get_prediction_detail` and `_prediction_probs` behaves sensibly.
- **Honesty requirement:** the UI must label these as reconstructed from a
  walk-forward backtest, not present them as live pre-game calls. A short note
  on the matchup page for any prediction whose model version starts with
  `backtest` is sufficient.
- SHAP factors: generate them if cheap, otherwise store an empty list. The
  narrative should be null; do not spend Claude calls narrating thousands of
  historical games.
- Idempotent, and re-runnable per sport and season.

### 7.4 Temporal-disjointness guard

Add an assertion in `ml/train.py` that no training row's kickoff is at or after
the earliest kickoff of the calibration set, and a test covering it. This is the
guard that makes a future mid-season retrain safe (§4).

## 8. Frontend: finished games

The explorer identified exact seams; use them rather than redesigning.

**Game card** (`frontend/src/components/GameCard.tsx`):

- **Score** goes in the existing right-aligned `ml-auto` slot in `TeamRow`
  (`GameCard.tsx:38-46`), already `font-mono tabular-nums` with a
  favored/unfavored emphasis split. The winner takes the emphasis the favored
  team currently gets.
- **Verdict badge** goes in the meta row's `ml-auto` slot (`:111-117`), already a
  branch holding either the pending label or the hover arrow. Style it like the
  Prime-time pill (`:107`).
- **Third bar state**: the win-prob bar / hatched-pending ternary (`:86-98`) is
  the template for a "FINAL" treatment.
- `game.status` is currently unused across the entire UI; leave it unused and
  drive off scores.

**Matchup page**:

- Derive `const final = ...` next to the existing `pending`
  (`MatchupHero.tsx:69`, `ReasoningPanel.tsx:17`) and branch the same two places.
- Final score belongs in `TeamColumn`'s large numeric block
  (`MatchupHero.tsx:49-62`), which already renders a huge number with a caption.
- Verdict band goes in the hero's state-dependent bottom band
  (`MatchupHero.tsx:102-131`). Colors there sit on the turf gradient, not
  `--surface`.
- A "Final" pill fits the meta line's existing `Badge` component
  (`MatchupHero.tsx:8-14,76-88`).
- `ReasoningPanel.tsx:18` already computes the model's pick (`favored`), which is
  exactly what a verdict check needs. Post-hoc verdict copy goes above the
  narrative (`:37-43`).
- `StatTicker` (`:49-56`) is a `[label, value][]` array; adding a result cell is
  a one-line change.

**Card state matrix** (all four must render):

| Scores | Prediction | Render |
|---|---|---|
| no | no | pending strip, "Prediction pending" |
| no | yes | current predicted state |
| yes | yes | score + verdict badge |
| yes | no | score, **no** verdict badge |

## 9. Frontend: filters

Filter state lives entirely in the URL; there is no client filter state
(`app/[sport]/page.tsx:16-23,203-214`).

- CFB filtering is a single predicate over the games array
  (`page.tsx:165-170`). A status filter is one more clause.
- **`filterQuery` (`page.tsx:172`) must carry the status param**, or the filter
  drops when the user changes week.
- **NFL has no `FilterChips` at all** (`page.tsx:98-133`) and passes no `query`
  to `WeekSelector` (`:125`). Both need adding.
- `FilterChips` hardcodes `/cfb` (`FilterChips.tsx:24-25`) and is
  conference-aware. **Build a separate shared `StatusFilter` component** rather
  than growing `FilterChips`.
- Validate the param against known values and fall back silently, matching the
  existing `activeConf` pattern (`page.tsx:163`).
- The `filtered` boolean (`page.tsx:197`) drives empty-state copy
  (`:71-78`); a status filter that matches nothing must produce the "no games
  match these filters" message, not "no games scheduled".
- The "X/Y predicted" counter (`page.tsx:110,171`, rendered `:121-123,183-185`)
  should read "X/Y correct" for a fully completed week.

**Default week.** `pickDefaultWeek` (`lib/format.ts:75-85`) keeps a week current
until 6h past its **last** kickoff, then jumps forward.

Every NFL week ends with Monday Night Football at 8:15 PM ET (verified against
the 2026 schedule, weeks 1 through 5). So the week is still current all day
Monday, because MNF has not kicked off yet. The rollover points are:

| Hold | Rolls over |
|---|---|
| 6h (current) | Tue 2:15 AM ET |
| 12h | Tue 8:15 AM ET |
| 36h | Wed 8:15 AM ET |

**Decision: 12 hours.** Monday night's result stays up overnight, and the week
rolls as people start their Tuesday. 6h rolls at 2 AM, before anyone would see
it; 36h holds through all of Tuesday and into Wednesday, by which point the
audience has moved on to Thursday night.

CFB uses a separate calendar-based path, `pickCfbDefaultWeek`
(`lib/format.ts:94-100`, Monday 00:00 ET). **Leave it unchanged.** CFB games end
Saturday night, so Sunday already serves as the review day.

Change the constant, update the existing `pickDefaultWeek` tests, and add cases
pinning Monday-evening and Tuesday-morning behavior.

## 10. Frontend: record display

Top of the slate page. Shows Blitzcast's current-season correct/total and
percentage next to the market's over the same games, with the sample size
visible.

- Below the `sufficient` threshold, render "not enough games yet" rather than a
  percentage.
- Never show the model's number alone; the market baseline is what keeps it
  honest.
- Must not imply the model beats the market. It does not.

## 11. OG share images

Highest-leverage item for a site people paste into group chats. Today
`openGraph` (`app/[sport]/matchup/[gameId]/page.tsx:37`) declares no image, so
shares render as bare text.

- Use Next's file-based `opengraph-image` convention under the matchup route.
- Content: both teams, the win probability, and Blitzcast branding. For a
  finished game, the score and verdict.
- Add a `twitter` card alongside.
- Requires `metadataBase` to resolve, which now reads `NEXT_PUBLIC_SITE_URL` /
  `VERCEL_URL` (`app/layout.tsx`). Set `NEXT_PUBLIC_SITE_URL` on Vercel.
- Verify the generated image renders in the deployed environment, not just
  locally; font loading in the OG runtime is the usual failure mode.

## 12. Model vs market disagreements

Both numbers already exist. Surface the largest gaps between the model
probability and the de-vigged market probability for the current week.

- Reuse `market_home_prob` semantics (`ml/features.py:92-100`).
- Exclude games with no market data.
- Frame it as interesting, not as a betting edge. The site says "not betting
  advice" and that must remain true in tone as well as in the disclaimer.

## 13. Methodology page

A static route explaining, in plain language: what the model uses, the
leakage rule, that Claude narrates but never predicts, and how often the model
is wrong including the honest comparison to Vegas. Source material is already in
`README.md` and `DECISIONS.md`.

Mostly writing. No em dashes; match the existing broadcast voice.

## 14. Sitemap and robots

`app/sitemap.ts` and `app/robots.ts`. Include both slates and matchup URLs.
Sitemap generation must not fetch the entire season on every request; cache or
bound it.

## 15. Edge cases to handle explicitly

| Case | Required behavior |
|---|---|
| Tie game | `prediction_correct = null`; no verdict badge; excluded from record |
| `home_win_prob == 0.5` | `prediction_correct = null`; excluded from record |
| Final game, no prediction | Score renders; no verdict badge; excluded from record |
| Final with `home_score` set but `away_score` null | Treated as **not** final |
| Game with no market data | Excluded from both record counts |
| Backfilled prediction | Labeled as reconstructed; excluded from live record |
| Fewer than threshold games | Record shows "not enough games yet" |
| Status filter matches nothing | "No games match these filters" |
| Unknown `?status=` value | Falls back to "all" silently |

## 16. Known limitations to document, not fix

- **CFB postseason is never loaded.** `cfbd.load_games` hardcodes
  `seasonType="regular"` (`data_pipeline/cfbd.py:44-45`), so bowl and playoff
  results never arrive. `CFB_WEEKS = 15` (`lib/format.ts:87`) has no postseason
  weeks either. Note it in the docs; fixing it is a separate change.
- **No live/in-progress state.** Neither loader writes anything but
  `scheduled` or `final`.
- **`predicted_at` ties** make ordering nondeterministic in
  `get_prediction_detail` and `_prediction_probs`. Plausible for bulk-inserted
  backfill rows, so set distinct timestamps in §7.3.
- Holdout metrics in `train.py` remain optimistic; `backtest.py` is the honest
  number and is what the README quotes.

## 17. Design language

All tokens live in `frontend/src/app/globals.css` and must be added in **three
places**: `:root` (light, `:9-25`), `:root[data-theme="dark"]` (`:27-43`), and
`:root:not([data-theme="light"])` under `prefers-color-scheme: dark` (`:46-64`),
plus the `@theme inline` mapping (`:66-82`) to get Tailwind utilities.

There is **no** success/failure token today. Two hazards:

1. **The brand is already green.** `--stripe-a`/`--stripe-b` are turf greens and
   `--ink` is near-black green. A green "correct" badge reads as chrome, not as
   a verdict. Gold is already spent on favored/active/hover.
2. **Two surfaces.** Verdict colors appear on `--surface` (cards) and on the
   `.turf` gradient (hero). Expect a paired token per verdict, exactly as
   `--gold-text` and `--gold-turf` are paired today.

**Accessibility is a hard requirement, not a nicety.** Color alone fails WCAG
1.4.1, and red/green is the worst possible pair for deuteranopia and
protanopia. Every verdict must carry a word ("Called it" / "Missed") or a glyph
in addition to color, matching the existing convention: `TbdBadge` says "Time
TBD" with a dashed border, and the pending state uses both the word and the
`.hatch` texture. New tokens need AA contrast in both themes at the
`text-[9px]`/`text-[10px]` sizes these badges use.

## 18. Testing requirements

**Backend.** Unit tests for: the verdict rule including all three null cases;
the status filter including the unknown-value fallback; the record endpoint
including the insufficient-sample state and market-baseline sample parity;
`predict_week` skipping final games; `default_week` not sticking; the
temporal-disjointness guard; backfill idempotency.

Note `tests/conftest.py` uses in-memory SQLite, so anything Postgres-specific
(e.g. `DISTINCT ON`) will not work. Keep queries portable.

**Frontend.** Tests for all four card states in §8, the verdict rule at the
component level, the status filter surviving week navigation, and the record's
insufficient-sample state.

**Contract parity.** Any field added to a schema must be added to
`app/mock_data.py` and to `frontend/src/lib/mock.ts` / `mockCfb.ts`, and covered
by `frontend/src/lib/__tests__/api.test.ts`. Three separate contract-drift bugs
have already shipped in this repo; this is the check that prevents a fourth.

**Chrome.** Extensive manual verification is required before this is considered
done, on real data with the backend running, not mock mode:

- Both sports, a completed week and an upcoming week.
- All four card states from §8.
- Verdict colors in **both** light and dark themes, on cards and on the turf hero.
- Status filter: each value, plus surviving a week change, plus the empty state.
- Record display, including the insufficient-sample state.
- Neutral-site and TBD-kickoff games still render correctly.
- OG image renders for a matchup.
- Mobile viewport.
- Note: after switching out of mock mode, delete `frontend/.next` or Next serves
  cached mock-mode 404s.

## 19. Constraints

- **Do not commit. Do not push.** All work stays in the working tree for review.
- Ships as **v1.0.0**; no version bump, no new model version. Backfilled
  predictions use a distinct `backtest-*` version string, which is a data label,
  not a release version.
- The leakage rule stands: every feature for game G uses only data from strictly
  before G's kickoff. Tests enforce it; keep it that way.
- Claude narrates model output only. It never predicts and never alters
  probabilities.
- Branding is "Paymon Software" only. Never the maintainer's real name.
- Comments minimal, clean, simple. Ruff-clean, ESLint-clean.
- No em dashes in user-visible copy or in the narration prompt.

## 20. After implementation

In order, once everything works and all tests pass:

1. **Code review** across backend and frontend.
2. **Security review** of the diff.
3. Fix what those surface.
4. **Update all docs and `.md` files for v1.0.0**: `README.md`, `CHANGELOG.md`,
   `backend/README.md`, `frontend/README.md`, `DECISIONS.md`, `CLAUDE.md` if
   conventions changed. Record the new endpoints, the status filter, the
   backfill job, and the known limitations from §16.
5. Delete `PROGRESS.md`.
6. Re-run the full suite and a final Chrome pass.
7. Hand back for review. Still no commit.
