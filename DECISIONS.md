# DECISIONS.md

Concise log of significant technical decisions: what / why / alternative considered.
Kept for the owner's reference (interview prep, future maintenance).

## Walk-forward backtesting instead of random k-fold

Model is validated season-by-season, expanding-window (train on seasons up to N, predict
season N+1, roll forward), never randomly shuffled cross-validation. **Why:** random k-fold
leaks future games into training when the target is inherently time-ordered. A model that's
never seen 2025 results has no business being validated on a random split that includes them.
**Alternative:** standard k-fold CV: faster to run, but the resulting metrics would be
meaningless for a system meant to predict future games from past ones; rejected.

## Difference features over raw absolute features

Model inputs are mostly home-minus-away deltas (`elo_diff`, `epa_off_diff`, `rest_diff`) rather
than separate home/away columns. **Why:** smaller, more stable model on a limited dataset
(~1,080 training games), and a cleaner SHAP story: "+0.14 from home Elo edge" reads better
than four separate absolute-value contributions that the reader has to mentally subtract.
**Alternative:** keep home and away features separate and let the tree model learn the
interaction: plausible with more data, but adds variance without a matching sample size.

## Calibration treated as a first-class metric, not an afterthought

Model probabilities are calibrated (Platt/isotonic) against a time-aware holdout, the most
recent season, not a random subset. **Why:** tree-based classifiers are frequently
overconfident; without calibration a "70%" prediction might really only win 55% of the time,
which defeats the purpose of reporting a probability at all. **Alternative:** report raw model
output uncalibrated: simpler, but the number would be decorative rather than meaningful;
rejected.

## Vegas closing line as the validation baseline, not just an accuracy target

Every backtest reports the model's Brier score and log-loss next to the same metrics computed
from the market's closing-line implied probabilities. **Why:** "63% accurate" means very little
on its own. Comparing against the market (one of the hardest baselines to beat, using only
public data) is the actual evidence the model is doing something real, and an honest result
either way is worth reporting. **Alternative:** report accuracy/AUC only: easier to make look
good, but doesn't tell a reader anything about whether the model is actually well-calibrated or
competitive; rejected.

## Batch-generated predictions, not per-request inference

Predictions are computed on a schedule (after each weekly data refresh) and written to Postgres;
the API only ever reads cached rows, never runs the model live on a request. **Why:** several
upstream data sources (odds, weather) are rate-limited free tiers, and per-request inference
would make API usage unpredictable and the app slower for no real benefit, since odds/injuries
don't change minute-to-minute. **Alternative:** run inference on each API call: simpler
mentally, but ties app latency and external API budget to traffic; rejected.

## Anti-leakage as an explicit, tested property of feature engineering

Every rolling feature (Elo, EPA/play, form) is computed strictly as-of the week before the
target game: nothing derived from data at or after kickoff. This is enforced with a dedicated
test, not just a coding convention. **Why:** leakage is the most common way a "surprisingly
good" backtest turns out to be fake; a model that accidentally sees the outcome it's predicting
will look great in testing and useless in production. **Alternative:** trust careful coding
without a leakage-specific test: too easy to silently regress when the pipeline changes;
rejected.

## SHAP for explainability instead of a black-box probability only

Each prediction ships with the top contributing features (signed, human-labeled) via SHAP
TreeExplainer, not just a bare percentage. **Why:** a probability without reasoning is much less
useful and much less trustworthy: showing which factors moved the needle (and in which
direction) makes the model's behavior auditable and the output far more interesting to read.
**Alternative:** ship the probability alone and skip explainability: simpler to build, but
turns the model into a black box with no way to sanity-check individual predictions; rejected.

## LLM narration layer strictly downstream of the model, never upstream

The narration step receives the model's probability and SHAP factors as fixed inputs and only
turns them into prose: it cannot change the numbers, and a failed narration falls back to
showing the factor list without prose rather than blocking the prediction. **Why:** keeping the
actual prediction deterministic and testable was the whole point of using a real ML model in the
first place; letting a language model touch the math would undermine the backtest results
entirely. **Alternative:** let the LLM generate both the number and the explanation together:
faster to prototype, but non-deterministic and impossible to validate rigorously; rejected.

## CFB added as a `sport` discriminator, not a fork

College football shares one Postgres DB and one FastAPI app with NFL: `sport=NFL|CFB` is a
query param on the schedule/games/teams endpoints and a `--sport` flag on the ML CLI commands
(`compute_ratings`, `train`, `backtest`, `predict_week`), rather than a second copy of the
codebase. Each sport still gets its own Elo history, trained model, and calibration
(`ml/reports/backtest_cfb.md`, `ml/artifacts/cfb/`), since NFL and CFB have genuinely different
score distributions and shouldn't share one model. **Why:** the app-layer code (API contract,
prediction batch shape, frontend components) is sport-agnostic and would otherwise be duplicated
wholesale for one extra query param's worth of difference; only the parts that are *actually*
sport-specific (data sources, model artifacts, injury-data availability) diverge.
**Alternative:** a separate `cfb-blitzcast` app/repo: clean isolation, but doubles the
maintenance surface for routing, schemas, and frontend chrome that don't differ by sport;
rejected.

## Haiku 4.5 as the default narration model, Sonnet as an override

`ANTHROPIC_MODEL` defaults to `claude-haiku-4-5-20251001` (`backend/app/config.py`), not a
larger model, and is a setting rather than a literal scattered through `narrate.py`. **Why:**
narration output is short (2–4 sentences) and high-volume-ish (~16 NFL + ~65 CFB games/week);
Haiku's latency and cost are negligible at that volume and the task (restating given numbers in
an energetic voice) doesn't need a frontier model's reasoning. **Alternative:** hardcode Sonnet
for consistently higher prose quality: plausible if narration quality ever becomes the
bottleneck, which is exactly why it's a config override, not a rewrite, away.

## Odds API: one batch call per day, never per request

The Odds API's free tier (500 requests/month) is called once daily by the scheduled refresh job,
which returns all of that week's games in a single response, never invoked on a user request.
**Why:** at 30 calls/month this leaves comfortable headroom under the free-tier cap regardless of
site traffic, and odds don't move meaningfully minute-to-minute, so there's no UX cost to reading
a cached row instead of a live call. **Alternative:** fetch fresh odds per matchup-detail page
view: simple to reason about, but ties API budget directly to traffic and would blow through
500 requests/month almost immediately; rejected.

## Completion keyed on scores, never on `Game.status`

Every place that needs to know whether a game is over (the `?status=` filter, the verdict
badge, the season record) checks `home_score is not None and away_score is not None`, never the
`Game.status` column. **Why:** `status` is a derived, unindexed column that NFL's own loader has
set to final on the home score alone in the past; a filter or a grading query built on top of it
would inherit that bug silently. The two score columns are the actual source of truth written by
the data pipeline, and checking them directly can't drift out of sync with itself.
**Alternative:** trust and maintain `Game.status` as the single flag: fewer columns to check per
call site, but re-introduces exactly the class of bug (a home-score-only final check) this feature
was built to leave behind; rejected.

## Backfilled predictions from walk-forward retraining, not the shipped model

`app/jobs/backfill_predictions.py` reconstructs 2023-2025 predictions with a model retrained per
holdout season that has never seen that season, mirroring `ml/backtest.py`, rather than by simply
running the shipped `1.0.0` artifact over historical games. **Why:** the shipped model trained on
2023-2025, so scoring it against those same seasons would be in-sample and read as a far better
season record than the model has ever actually produced on unseen games. Rows are stamped with a
distinct `backtest-*` model version specifically so they can never leak into `/api/record` or the
slate's live probability. **Alternative:** run the shipped model over history for speed and
simplicity: much less code, but the resulting "season record" would be a quiet lie about how the
model performs on games it hasn't trained on; rejected.

## No mid-season retrain for this release

The model is not retrained partway through the 2026 season even though a finished-games feature
now exists to grade it. **Why:** Elo and the rolling-form features already adapt within a season
without retraining the model itself, and widening `TRAIN_SEASONS` mid-season would need its own
validated methodology (what counts as calibration data, how to avoid leaking the very games being
graded) before it's safe to ship. `assert_temporally_disjoint` in `ml/train.py` was added now so
that whenever that methodology exists, a training/calibration window overlap fails loudly instead
of quietly leaking. **Alternative:** retrain on a rolling window as the season progresses: would
keep the model fresher, but without a validated split it risks training on games close enough to
the calibration window to leak; rejected for this release.

## Record always paired with the market baseline, never shown alone

`/api/record` and `RecordBanner` never surface the model's accuracy without the market's accuracy
over the identical graded sample, and `RecordBanner` explicitly documents this as a rule in its
own comment. **Why:** a bare "65% correct" reads as a claim of skill it can't back up alone; the
whole point of comparing to Vegas throughout this project (see the walk-forward backtest decision
above) is that a number is only meaningful next to a real baseline, and the live in-season record
deserves the same standard as the backtest report does. **Alternative:** show the model's number
by itself and let a reader visit the backtest report for context: technically available, but
defeats the purpose of putting a record on the page at all if the one number shown is the
misleading one; rejected.

## No season selector for this release

The slate always renders the current season (2026); the 2023-2025 backfilled history is reachable
only via a direct matchup URL by game id, not through any slate navigation control. **Why:** a
season selector is a real, separate piece of UI and routing work, and this release's actual goal
was grading the live model against the market, not building a historical archive browser.
Reconstructed predictions are already labeled as such wherever they're reachable, so nothing about
leaving them nav-inaccessible is dishonest, it's just not built yet. **Alternative:** ship a season
dropdown now: would make the backfilled data browsable, but expands this feature's scope well
beyond the finished-games work it was meant to deliver; deferred, not rejected outright.

## Frontend and backend as separate services, not a monolith

Next.js (`frontend/`) and FastAPI (`backend/`) are two processes communicating over an internal
HTTP API, not a single full-stack framework serving both. **Why:** the ML/data pipeline is a
Python-native problem (XGBoost, SHAP, nflverse/CFBD tooling) with no good equivalent in the
Node ecosystem, and a typed API contract (`src/lib/types.ts` mirroring the FastAPI schemas) keeps
the frontend swappable or independently deployable later. **Alternative:** a Python-rendered
frontend (e.g. Jinja/HTMX): would avoid the contract-sync overhead, but trades away Next.js's
component/theming ergonomics for a UI that's meant to look polished and be mobile-friendly;
rejected.

## Committing the trained model artifacts, as an exception

`backend/ml/artifacts/` is gitignored by default (only `latest.json` is normally tracked), but
the two current *latest* model files (`model_1.0.0.joblib`, `model_cfb-1.0.0.joblib`) are a
deliberate exception, carved out in `.gitignore`. **Why:** `ml/train.py` pins no random seed, so
retraining on a fresh machine (a deploy target, for instance) would not reproduce these exact
weights, and the accuracy numbers already published in `README.md` and the `/how-it-works` page
describe these specific files, not whatever a new retrain would produce. The files themselves are
small (roughly 350KB combined), so committing them costs nothing in repo size. **Alternative:** a
Railway Volume with a manual upload step, or retraining as part of first deploy: both add
infrastructure or a determinism risk to solve a problem the tiny file size doesn't actually pose;
rejected for this release. Whoever retrains the model (season-end only, see the walk-forward
backfill decision above) needs to re-commit the new file and update the `.gitignore` exception if
the filename changes.

## Short revalidation window over `no-store` for slate/matchup fetches

The frontend's API client caches every GET for 30 seconds (`next: { revalidate: 30 }`) instead of
bypassing the cache entirely. **Why:** predictions only change on the weekly cron refresh, so
`no-store` bought no real freshness — every week-selector click was a live Vercel-to-Railway-to-
Postgres round trip, which read as instant on desktop broadband but was a noticeable stall on
mobile/cellular, especially for CFB's larger per-week payload. A 30-second window is short enough
that a mid-refresh visitor never sees meaningfully stale odds, and long enough to absorb repeat
navigation within a single browsing session. **Alternative:** a longer window (minutes) tuned
tighter to the cron cadence: would cache more aggressively, but risks a visitor seeing a stale
score during a live game for no real latency benefit over 30 seconds; rejected.

## Scoping `frame-ancestors` instead of leaving embedding unrestricted

`frontend/next.config.ts` now sends `Content-Security-Policy: frame-ancestors 'self'
https://cartertull.com https://www.cartertull.com` on every route. **Why:** the app previously
sent no framing-control header at all, so any site could iframe blitzcast.app for clickjacking —
a gap that only became worth closing once the portfolio at cartertull.com started deliberately
embedding it in a window. Scoping to the two origins that need it (the portfolio, plus `'self'`
for blitzcast.app's own pages) closes the general hole without breaking the one embed that's
supposed to work. No `X-Frame-Options` is set alongside it: it can't list multiple origins, and
CSP's `frame-ancestors` overrides it in every browser that honors both, so it would be dead
weight rather than a fallback. **Alternative:** leaving embedding unrestricted: simplest, but
that's the clickjacking gap this closes; rejected.

## Neutral-site games capture a raw venue name instead of relying on Team.stadium_id

`Game.venue_name` and `Game.is_neutral_site` are new columns, populated straight from
nflverse's `stadium`/`location` schedule fields. **Why:** `stadium_id` was being derived purely
from the home team's normal home stadium, so any neutral-site game (an international game, or
any row where nflverse's `location` isn't `"Home"`) got `stadium_id = NULL` with zero venue
information recoverable anywhere downstream — this broke both weather (`refresh_weather.py`
skipped it identically to a dome) and the matchup page (blank venue block). Confirmed via
nflverse's own schedule data that the raw venue name (e.g. "Melbourne Cricket Ground") is
already present in the feed and simply wasn't being read. Weather for these games is now fetched
by geocoding the venue name string through Visual Crossing rather than lat/lon, since most
international venues have no `Stadium` row. **Alternative:** seed a `Stadium` row for every
possible international venue in advance: more precise (real lat/lon, dome status) but requires
maintaining a venue list by hand every season as the international slate changes; venue-name
geocoding needs no maintenance and degrades to a clean failure (skip, not a wrong answer) if
Visual Crossing can't resolve a name.

## Market-factor SHAP direction is grounded in the raw value, not the SHAP sign

`ml/explain.py`'s `top_factors()` derives `direction` for `market_spread_home` and
`market_home_prob` from the feature's own raw value (positive/`>0.5` = home favored), not from
whether that feature's SHAP contribution was locally positive or negative. **Why:** which team
the betting market favors is an independently checkable fact, not a model inference — but a
tree ensemble's SHAP attribution for one feature can point the opposite way from that feature's
own value near a toss-up line (reproduced live: `cfb_401856682`, OSU@TEX Week 2 2026, had
`market_spread_home = +1.5` — home/Texas favored, matching the live odds — while its SHAP
contribution was negative, so the narration said the market favored Ohio State). Confirmed this
wasn't stale data or a column-order bug by rebuilding the feature row from the live database and
reproducing the identical SHAP sign. No other feature has this treatment, since none of the
others have an independent ground truth to check against — SHAP sign is still the right answer
for e.g. `elo_diff`. **Alternative:** leave SHAP sign as the sole source of truth for every
feature: simpler, and defensible as "faithfully describing the model," but it lets the narration
state something checkably false about real market data, which conflicts with the LLM boundary
principle that narration should never contradict real numbers. **No `MODEL_VERSION` bump**: the
model's weights and features are unchanged; only how a factor's direction is *labeled* changed.

## Narration guardrail checks favorite/underdog attribution, not just percentage magnitude

`narrate.py`'s `_percentages_consistent` guardrail only ever checked that a cited percentage's
*magnitude* matched the home/away win probability, never which *team* it (or "favorite"/"the
edge" language) was attached to. **Why:** found live in production — three CFB Week 1 2026
narrations correctly cited the model's own percentage while calling the underdog "a slight
favorite" (`cfb_401858210`, `cfb_401856677`, `cfb_401864502`), passing the existing check because
the number was right even though the team label wasn't. Added
`_favorite_attribution_consistent`: for each "favorite"/"favored" mention, the nearest team name
appearing *before* it in the same sentence must be the real favorite. **Known gap:** matches only
a team's school name/abbreviation, not mascot nicknames (e.g. "the Bruins" for UCLA) — a
narrative that names only the mascot isn't checked. **Alternative:** a full team-name-to-mascot
dictionary for exhaustive coverage: meaningfully more complete, but a much larger maintenance
surface (every FBS + NFL mascot) for a guardrail whose failure mode is just "retry, then fall
back to no narration" rather than showing wrong data; can be revisited if mascot-only phrasing
turns out to be common.

## CFBD's -100000 "no quote" sentinel filtered at ingestion, not just at use

`data_pipeline/cfbd.py`'s `load_lines()` now converts any moneyline with `abs(value) >= 100_000`
to `None` before it ever reaches the database; `ml/features.py`'s `market_home_prob()` carries
the same guard defensively. **Why:** CFBD returns `-100000` as a "no real price quoted" marker on
the extreme side of lopsided blowouts, not a genuine price. Found live: 12 CFB Week 1/2 2026 rows
(e.g. `cfb_401856665`, a 57-0 game) had this stored as a real moneyline, which corrupted the
de-vigged `market_home_prob` toward 0.5 for a real blowout instead of falling back to the spread.
**Alternative:** guard only in `market_home_prob()`: would fix the derived feature but leave the
misleading sentinel sitting in `games.home_moneyline`/`away_moneyline` for any other consumer
(the raw odds display, future features) to trip over again; fixing it at the ingestion source is
the same cost and closes the whole class of bug.

## A second, separate narration guardrail for market-specific attribution

`_favorite_attribution_consistent` checks favorite/underdog language against the *model's own*
win probability; a distinct `_market_attribution_consistent` checks it against the *raw spread*,
scoped only to sentences that reference the market (Vegas/the line/the spread/etc). **Why:**
regenerating predictions after the first attribution fix landed, this exact split surfaced live
on the fix's own target game (`cfb_401856682`, OSU@TEX): the model favors Ohio State overall, so
"Ohio State favored" passed the general check even in a sentence that was actually describing
what Vegas thinks (which favors Texas). The model is allowed to disagree with the market; a
sentence attributing an opinion to Vegas specifically is not allowed to get Vegas's opinion
wrong. **Alternative:** one combined guardrail that always checks favorite language against
whichever ground truth (model or market) is "the real one": there isn't a single real one —
model-vs-market disagreement is a legitimate, common, desired thing to narrate — so the two need
separate, differently-scoped checks rather than one.

## CFB weather wired into the daily cron after all

`refresh_week_cfb.py` (run daily by Railway's cron, not weekly) now includes a
`refresh_weather --sport cfb` step. **Why:** the original decision to omit it assumed CFB had no
stadium coordinates to fetch weather by; that's wrong — CFBD's own venue data gives CFB games a
real `Stadium` row (unlike NFL, which derives `stadium_id` from the home team), confirmed by
manually running `refresh_weather --sport cfb` and getting real weather for 85 of 86 games. The
free-tier budget concern was real but re-checked: an 8-day CFB slate is at most ~170 games/day,
comfortably under Visual Crossing's 1000 records/day even alongside NFL's own daily run.
**Caveat, not a reason to skip this:** the already-trained CFB model saw zero-variance weather in
every historical row (never populated before), so its trees have no split on temp/wind/precip —
this is purely a display and future-training improvement, not something that changes any current
prediction. **Alternative:** leave it manual-only, as discovered: works, but relies on someone
remembering to run it every week: the automated version costs nothing extra worth worrying about
at this volume and removes that dependency on manual upkeep.

## Root-caused the intermittent 503s: disable prefetch on the week selector, not a backend fix

`WeekSelector`'s `<Link>`s now render with `prefetch={false}`. **Why:** reproduced live by
navigating the site while watching Vercel's dashboard: rapid week/sport switching triggered a
burst of near-simultaneous RSC prefetch requests (several sharing the exact same `_rsc` cache
token), and several came back 503. Vercel's Firewall showed the actual cause: its own automatic
DDoS mitigation was denying/challenging the burst (23 denied + 2 challenged requests in one
hour), not a backend or database problem — confirmed separately via Railway's logs/metrics
showing 0% error rate the whole time. Next.js prefetches every visible `Link` by default; the
week selector renders every week (up to 18) at once, so simply having that row mount fires that
many near-simultaneous requests without requiring a real visitor to click quickly at all.
**Alternative:** upgrade to Vercel Pro for System Bypass Rules: doesn't actually help, since
bypass rules only exempt IPs you name in advance, not arbitrary real visitors; the fix has to be
not generating the burst in the first place.

**Follow-up:** the week selector alone wasn't enough — re-running the same live reproduction
against the deployed fix still 503'd. `GameCard` (10-16+ links per slate page) turned out to be
the dominant contributor, plus smaller lists in `StatusFilter`, `FilterChips`, and
`Disagreements`, plus `Header`'s sport toggle (renders on every page). All got the same
`prefetch={false}` treatment; true singleton nav links (logo, footer, matchup back-link) were
left alone since one instance per page can't create a burst.
