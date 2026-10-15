# Security Hardening (v1.2.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the real findings from the 2026-10-15 repo-wide review (CodeQL plus four parallel reviewers), without changing the model, the stored predictions, or anything a visitor sees beyond safer headers.

**Architecture:** Six tasks on one branch `ct/fix/security-hardening`, one commit each, released as v1.2.3. Tasks 1 to 5 are independent code areas (CI and headers, frontend params, backend API, narration guardrails, pipeline and ML); Task 6 is docs, diagrams and the version bump.

**Tech Stack:** FastAPI + SQLAlchemy 2 + pytest; Next.js 16 + Jest; GitHub Actions; Mermaid docs.

**Spec:** the user's request (2026-10-15): enable CodeQL, scan the repo, patch what needs patching, keep everything working, bump the version, update docs and diagrams, release. Findings and rulings are in the review ledger summarized under "Findings in scope" below.

## Global Constraints

- **Authorship:** every commit is made with the existing git identity. Never pass `--author`, never run `git config`, no `Co-Authored-By`, no `Claude-Session:` trailer, no session URL, no "Generated with" line.
- **Branding:** "Paymon" / "Paymon Software" only; never the maintainer's real name or personal email in code, comments or docs. The portfolio origins in `frontend/next.config.ts` `frame-ancestors` are the one existing functional exception: keep them exactly as they are and do not copy them anywhere else.
- **Copy:** no em or en dashes in anything a visitor can see; check `&mdash;`/`&ndash;` too.
- **No production writes, no paid API calls.** Tests must mock Anthropic, the Odds API, CFBD, Visual Crossing and ESPN.
- **Model untouched:** do not retrain, do not change `.joblib` bytes, `MODEL_VERSION` stays `1.0.0` / `cfb-1.0.0`. Adding a `sha256` field to `latest.json` is allowed (Task 5).
- **Invariants from CLAUDE.md stay true:** completion is `home_score is not None and away_score is not None` (never `Game.status`); the leakage rule; the LLM boundary (Claude never predicts; the booth always names the model's pick; the narration summary line format `narration: N written, K kept, F fallback, L minimal, J none` is unchanged); `app/market.py` is the single moneyline rule; jobs degrade gracefully when keys are missing.
- **Python:** ruff-clean, SQLAlchemy 2 typed style, pinned dependencies (add no new dependency).
- **Stage by explicit path.** One commit per task with the exact message given.
- **Version:** app 1.2.2 becomes **1.2.3** (patch: fixes and hardening only).

## Findings in scope (with the task that fixes each)

| Source | Finding | Task |
|---|---|---|
| CodeQL #1, #2 | `ci.yml` has no `permissions` block | 1 |
| Frontend L4 | checkout leaves the token in `.git/config` | 1 |
| Frontend L2, I3 | only `frame-ancestors` is sent; `X-Powered-By` exposed | 1 |
| Frontend L3 | docker-compose publishes Postgres on all interfaces | 1 |
| Frontend L1, I1 | OG image route renders any path uncached; `getMatchup` passes any id | 2 |
| Frontend I4 | sitemap has no `revalidate` export | 2 |
| API M1 | season-wide endpoints uncached on a public origin | 3 |
| API L1 | unvalidated `game_id`/`season`/`week` can 500 | 3 |
| API L2 | `/docs`, `/redoc`, `/openapi.json` public in production | 3 |
| API I1, I2 | CORS allows credentials and every method; no `nosniff` | 3 |
| LLM L1 | injury player names skip the name gate; echoed unfenced in retries | 4 |
| LLM L2 | no circuit breaker when Claude is down | 4 |
| LLM L3 | invisible format characters pass the output checks | 4 |
| LLM I1 | colon/semicolon and other dash characters only enforced the next day | 4 |
| Pipeline M1 | every job defaults to season 2026 | 5 |
| Pipeline L1 | orchestrator subprocesses and DB connects have no timeout | 5 |
| Pipeline I2 | CFB loader writes in-progress scores as if final | 5 |
| Pipeline L4 | `seed_cfb` stores CFBD logo/color unvalidated | 5 |
| Pipeline L5 | model artifacts loaded with no integrity check | 5 |
| Pipeline I6 | `alembic/env.py` breaks on `%` in a DB password | 5 |
| LLM I2 | DECISIONS lists team names as an uncovered residual (stale) | 6 |

## Deliberately deferred (recorded in DECISIONS by Task 6)

- Pipeline L2 (partial ESPN injury payload): both candidate fixes have failure modes (ESPN may omit teams with no injuries); needs a look at real payloads first.
- Pipeline L3 (weather leakage guard): filtering `captured_at < kickoff` would drop all historical NFL weather and change backtests; belongs to the parked P4 retrain.
- Pipeline I1 (orchestrator ignores odds/weather failures): by design; revisit with alerting.
- `.github/dependabot.yml` and SHA-pinned actions: version-update PRs would make Dependabot a would-be contributor, which the maintainer does not want; first-party actions with read-only tokens are low risk.
- API rate limiting (a new dependency) and `Literal` enums in `schemas.py`, `SecretStr` for keys, `--proxy-headers`, `GameSummary.status`: low value now.
- `TeamCrest` host allowlist on the frontend: Task 5 validates at seed time instead, so existing good logos are not broken.

## Review Focus

1. A legitimate game id must keep working everywhere: NFL ids like `2026_01_BUF_KC`, CFB ids like `cfb_401752873`, and any id shape in `backend/app/mock_data.py` and the frontend mocks. The same id rule is used on both sides (`^[A-Za-z0-9_-]{1,32}$`, matching `Game.game_id String(32)`).
2. The portfolio iframe and ESPN team logos must still work after the header change (no `img-src`, `script-src` or `default-src` added).
3. Cached API responses must never serve another request's parameters, and tests must not see stale cached data between test cases.
4. The circuit breaker must never change a probability, never skip storing a prediction, and must leave the narration summary line format unchanged.
5. Season default: today (October 2026) both sports must still resolve to 2026, so nothing changes in production until the calendar does.

---

### Task 1: CI token, headers, local Postgres binding

**Files:** Modify `.github/workflows/ci.yml`, `frontend/next.config.ts`, `docker/docker-compose.yml`. Create `frontend/src/lib/__tests__/headers.test.ts` (or extend an existing config test if one exists).

- [ ] **ci.yml:** add a top-level `permissions:` block with `contents: read` (directly under `on:`), and `with: persist-credentials: false` on every `actions/checkout` step (merge into an existing `with:` if present). Change nothing else.
- [ ] **next.config.ts:** keep the existing `frame-ancestors` origins byte-for-byte. Extend the CSP value to `frame-ancestors <existing origins>; base-uri 'self'; object-src 'none'; form-action 'self'`. Add `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()` to the same headers list (applied to every route, like the existing CSP). Set `poweredByHeader: false`. Do not add `default-src`, `script-src` or `img-src`.
- [ ] **Test (write first, see it fail):** import the config's `headers()` and assert the route list includes each new header with the exact value, the CSP still contains the original `frame-ancestors` directive unchanged, and `poweredByHeader === false`.
- [ ] **docker-compose.yml:** change the Postgres port mapping to `"127.0.0.1:5432:5432"`.
- [ ] **Gates:** from `frontend/`: `npm run lint && npm test && npm run build`.
- [ ] **Commit:** `fix(ci): read-only CI token, add security headers, bind local Postgres to localhost`

### Task 2: Frontend parameter validation

**Files:** Modify `frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/sitemap.ts`; tests in `frontend/src/lib/__tests__/api.test.ts` (and a new OG test only if the route can be unit tested without a renderer; otherwise test the shared validator).

- [ ] Add one exported validator in `frontend/src/lib/api.ts` (or the existing shared lib it fits best): `isGameId(id: string): boolean` using `/^[A-Za-z0-9_-]{1,32}$/`.
- [ ] `getMatchup(gameId)`: if `!isGameId(gameId)`, behave exactly like the existing not-found path (whatever `getMatchup` does today for a 404, so the page renders its normal not-found UI). Do not fetch.
- [ ] OG route: validate `sport` with the existing `isSportSlug` and `gameId` with `isGameId`; for an invalid param or a game the API reports as not found, return a 404 `Response` (no image). Keep the existing fallback image only for backend errors (5xx or network failure) on a valid-looking id. Replace `export const dynamic = "force-dynamic"` with `export const revalidate = 300`.
- [ ] `sitemap.ts`: add `export const revalidate = 3600` so the hourly refresh its comment describes actually happens.
- [ ] **Tests (first, failing):** `isGameId` accepts `2026_01_BUF_KC`, `cfb_401752873`, every mock id in `frontend/src/lib/mock.ts` and `mockCfb.ts`; rejects `..`, `a/b`, `a%00b`, an empty string and a 33-character id. `getMatchup("..")` does not call `fetch` and takes the not-found path.
- [ ] **Gates:** from `frontend/`: `npm run lint && npm test && npm run build`.
- [ ] **Commit:** `fix(frontend): validate matchup ids and cache the share image route`

### Task 3: Backend API hardening

**Files:** Modify `backend/app/main.py`, `backend/app/config.py`, `backend/app/routers/predictions.py`, `games.py`, `schedule.py`, `record.py`, `backend/.env.example`; create `backend/app/cache.py`; tests under `backend/tests/` (new `test_api_hardening.py` plus a fixture in the existing `conftest.py` that clears the cache before each test).

- [ ] **Param validation:** `game_id: str = Path(..., min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")`; every `season` query param `ge=2000, le=2100`; every `week` query param `ge=0, le=30`. Keep existing defaults. Invalid input returns 422, never 500.
- [ ] **Docs off by default:** add `api_docs: bool = False` to `Settings`; build `FastAPI(...)` with `docs_url="/docs"`, `redoc_url="/redoc"`, `openapi_url="/openapi.json"` only when `api_docs` is true, else `None` for all three. Add `API_DOCS=1` with a one-line comment to `backend/.env.example` so local docs still work. Leave `version="1.0.0"` alone (no longer exposed in production).
- [ ] **CORS:** `allow_credentials=False`, `allow_methods=["GET"]`, keep `allow_origins` and `allow_headers` as they are.
- [ ] **nosniff:** a small HTTP middleware that sets `X-Content-Type-Options: nosniff` on every response. No `Cache-Control` header (there is no CDN in front of Railway).
- [ ] **TTL cache:** `app/cache.py` with a thread-safe in-process cache: `cached(key: tuple, ttl_seconds: float, compute: Callable[[], T]) -> T`, a max of 256 entries (evict the oldest when full), and `clear() -> None`. Use it in the `/api/schedule` and `/api/record` routers only, key = `(route name, every query param value)`, TTL 60 seconds. Cache the response model (or the plain data), never the DB session.
- [ ] **Tests (first, failing):** `/api/predictions/a%00b` and a 33-character id give 422; `season=99999` and `week=99` give 422; `/docs` and `/openapi.json` give 404 with the default settings and 200 with `api_docs=True` (build a fresh app or patch settings as the existing tests do); a CORS preflight for `POST` is not allowed and responses carry no `access-control-allow-credentials: true`; every response has `x-content-type-options: nosniff`; two identical `/api/schedule` calls compute once (spy on the service) and different params compute separately; the cache clears between tests. Existing API tests stay green.
- [ ] **Gates:** from `backend/`: `.venv\Scripts\python -m ruff check . && .venv\Scripts\python -m pytest`.
- [ ] **Commit:** `fix(api): validate params, hide docs in production, tighten CORS, cache season-wide endpoints`

### Task 4: Narration guardrail hardening

**Files:** Modify `backend/app/services/fact_sheet.py`, `backend/app/services/narrate.py`, `backend/app/jobs/predict_week.py`; tests in the existing narration and predict_week test files.

- [ ] **Player names (LLM L1):** in the injuries builder, keep a row only if its cleaned player name also passes `_reads_like_a_name`; drop the row otherwise. Real names with suffixes ("Jr.", "III", apostrophes, hyphens) must still pass; add tests for those and for a prose-like name being dropped.
- [ ] **Retry message (LLM L1):** when `generate` sends a guardrail reason back to Claude for a retry, wrap the reason in `<checker_note>...</checker_note>` and keep the prompt's statement that tagged content is data, not instructions (extend the system prompt's existing data-not-instructions sentence to cover `checker_note` if needed). Test that the retry message contains the tags.
- [ ] **Invisible characters (LLM L3):** `unsafe_output` (used by `check_narration`, `still_true` and the minimal line) rejects any character whose Unicode category is `Cc` or `Cf`. Tests: a draft containing U+200B inside a URL-like token, U+202E, and U+E0041 are rejected; a normal draft passes.
- [ ] **Punctuation (LLM I1):** `check_narration` rejects `;` and `:` (matching what `still_true` and the template already enforce), and `plain_punctuation` also handles U+2012, U+2015 and U+2212 the same way it handles U+2013/U+2014. Tests for each.
- [ ] **Circuit breaker (LLM L2):** in `predict_week`, count consecutive games whose narration attempt ended in an API failure (exception, timeout, or connection error from the Anthropic client, as opposed to a guardrail rejection). After 3 consecutive API-failed games, or immediately on an authentication error, stop calling Claude for the rest of the run: remaining games go straight to the existing kept/template/minimal path. Print one extra line `narration: Claude disabled for the rest of the run after <reason>` when it trips. The existing summary line format is unchanged; the prediction itself is computed and stored exactly as before for every game. A successful Claude call resets the counter. Tests: 3 consecutive simulated API failures trip it and later games make no Claude calls; an auth error trips it at once; a guardrail rejection does not count; probabilities and stored predictions are identical with and without the breaker tripping.
- [ ] **Gates:** from `backend/`: ruff + full pytest.
- [ ] **Commit:** `fix(narration): gate player names, fence retry notes, reject invisible characters, stop calling Claude when it is down`

### Task 5: Pipeline and ML hardening

**Files:** Create `backend/app/season.py`; modify the season defaults in `backend/data_pipeline/refresh_week.py`, `refresh_week_cfb.py`, `refresh_schedule.py`, `refresh_schedule_cfb.py`, `refresh_stats.py`, `refresh_stats_cfb.py`, `refresh_injuries.py`, `refresh_polls_cfb.py`, `backend/app/jobs/predict_week.py`, `backend/app/jobs/coverage.py`; modify `backend/app/db.py`, `backend/data_pipeline/cfb_games_loader.py`, `backend/data_pipeline/seed_cfb.py`, `backend/ml/model_store.py`, `backend/ml/train.py`, both `latest.json` files, `backend/alembic/env.py`; tests under `backend/tests/`.

- [ ] **Season default (Pipeline M1):** `current_season(sport: str, today: date | None = None) -> int`: NFL returns `year if month >= 3 else year - 1`; CFB returns `year if month >= 6 else year - 1`. Use it as the argparse default everywhere the brief lists (keep `--season` overridable). Test: 2026-10-15 gives 2026 for both; 2027-01-20 gives 2026 for both; 2027-04-01 gives 2027 NFL and 2026 CFB; 2027-08-01 gives 2027 for both.
- [ ] **Zero-game season (Pipeline M1):** `predict_week` exits 1 with a clear message when the requested season has no games at all for the sport (distinct from "no unplayed games", which stays exit 0). Test both.
- [ ] **Timeouts (Pipeline L1):** `run_step` takes `timeout: float = 1800` and passes it to `subprocess.run`; on `TimeoutExpired` it prints `<name> timed out after <n>s` and returns False. The prediction batch steps in both orchestrators pass `timeout=5400`. `create_engine` gets `connect_args={"connect_timeout": 15}` (works for psycopg 3). Tests for the timeout path (mock `subprocess.run` to raise).
- [ ] **CFB scores (Pipeline I2):** in `cfb_games_loader.py`, write `home_score`/`away_score` only when the game is completed: if `completed` is explicitly false, store `None` for both scores; if `completed` is missing, keep today's rule (both points present means completed). Test: in-progress row with points and `completed=False` stores no scores; completed row stores them; missing flag with both points stores them.
- [ ] **Seed validation (Pipeline L4):** in `seed_cfb.py`, keep `logo` only if it matches `^https://a\.espncdn\.com/i/teamlogos/ncaa/[\w/.-]+\.png$` (else `None`); keep `color`/`alt_color` only if `^#?[0-9a-fA-F]{6}$` (store in the same format the code stores today; else `None`). Tests for good and bad values.
- [ ] **Artifact integrity (Pipeline L5):** `train.py` writes `"sha256": <hex of the artifact bytes>` into `latest.json` when it saves a model. `load_latest` rejects an `artifact` value where `Path(name).name != name`, and when `latest.json` has a `sha256`, verifies the file's SHA-256 before `joblib.load` and raises a clear error on mismatch. Add the correct `sha256` for each committed artifact to `backend/ml/artifacts/latest.json` and `backend/ml/artifacts/cfb/latest.json` (compute from the committed bytes; do not touch the `.joblib` files). Tests: both committed artifacts load and verify; a tampered byte fails; a `../x.joblib` name is rejected.
- [ ] **Alembic (Pipeline I6):** in `alembic/env.py`, pass the URL with `%` escaped as `%%` to `set_main_option`.
- [ ] **Gates:** ruff + full pytest from `backend/`.
- [ ] **Commit:** `fix(pipeline): season default from the calendar, step timeouts, final-only CFB scores, verified model artifacts`

### Task 6: Docs, diagrams, version 1.2.3

**Files:** `frontend/package.json` + lockfile (`npm version 1.2.3 --no-git-tag-version`), `CHANGELOG.md`, `DECISIONS.md`, `CLAUDE.md`, `backend/README.md` (env var `API_DOCS`, `current_season`), `SECURITY.md` (only if a statement there became untrue; mention CodeQL under nothing unless a fitting section exists), diagrams as below, every diagram footer, and this plan file.

- [ ] **CHANGELOG `[1.2.3]`** (date of the commit): intro "A security hardening release from a repo-wide review and the first CodeQL scan. No change to the model, `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`) or stored predictions." Sections `### Security` and `### Fixed` listing the items in "Findings in scope" in plain words, and `### Added` for CodeQL code scanning (default setup, weekly plus every PR). Note the operator-facing change: the API's `/docs` is off unless `API_DOCS=1`.
- [ ] **DECISIONS:** one entry "Repo-wide security review and CodeQL (2026-10-15)" with what was fixed, the deferred list above with one reason each, and the rule that Dependabot version updates stay off. Fix the stale sentence that lists team names and mascots as uncovered (only player names were left, and Task 4 closes that). Add short notes for: the in-process TTL cache on season-wide endpoints, the circuit breaker, and the calendar-based season default.
- [ ] **CLAUDE.md:** keep it short. Add to Conventions: the shared game id rule (`^[A-Za-z0-9_-]{1,32}$`, backend `Path` and frontend `isGameId`); `API_DOCS` off by default; season defaults come from `app/season.py`'s `current_season`, never a hard-coded year; `latest.json` carries a `sha256` that `load_latest` verifies, so retraining must write it (`train.py` does). Update the narration bullet if needed to mention the breaker line.
- [ ] **Diagrams** (follow `diagrams/README.md` syntax rules): `deployment-security.md` (Vercel node lists the new headers; GitHub subgraph gains a CodeQL node; API node notes docs off, GET-only CORS, nosniff, 60s cache on season-wide endpoints); `prediction-request-sequence.md` (the 60s cache on schedule/record if that path is drawn); `llm-narration-boundary.md` (invisible-character rule, colon/semicolon rule, player-name gate, circuit breaker); `daily-refresh-sequence.md` (step timeouts, calendar season default) if those details are drawn; all 11 footers `_Last updated: <date> · reflects v1.2.3_`.
- [ ] **Leftover checks:** `git grep -n "1\.2\.2" -- . ':!CHANGELOG.md' ':!frontend/package-lock.json' ':!docs/superpowers'` prints nothing; dash check on new prose; full frontend and backend gates.
- [ ] **Commit:** `chore(release): 1.2.3 changelog, decisions, docs, diagrams`
