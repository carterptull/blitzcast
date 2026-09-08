# Week 1 Check-in Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (chosen over subagent-driven-development because the tasks touch overlapping files in a small, interconnected surface — sequential inline execution by one worker avoids merge conflicts). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two confirmed data-correctness bugs found during the Week 1/CFB Week 2 check-in (neutral-site games silently lose weather + venue data; market-derived SHAP factors can misstate which team Vegas actually favors), while leaving everything else (Wednesday NE@SEA kickoff — confirmed correct; 503s on RSC prefetch — needs production log access we don't have) untouched or documented only.

**Architecture:** Backend-only schema + pipeline + explainability change, with a small, optional API/frontend surface addition (show the real neutral-site venue instead of a blank venue block). No ML retraining needed — the SHAP fix changes only how a `direction` label is derived from an already-correct feature value, not the model itself.

**Tech Stack:** FastAPI, SQLAlchemy 2.x + Alembic, pandas, xgboost/shap, Next.js/TypeScript frontend, pytest, ruff.

**Spec:** This session's investigation (see conversation) — no separate spec doc; findings are summarized in the Global Constraints and per-task context below.

## Global Constraints

- Leakage rule: N/A — no training-feature changes, only explainability display logic and pipeline-ingest logic.
- Completion invariant: never key "is this game over" off `Game.status`; always check `home_score is not None and away_score is not None` — do not touch existing grading logic, but do not violate it in any new code either.
- LLM boundary: `narrate.py` must never contradict real market data — the SHAP-direction fix is in service of this rule.
- Adding an API field (CLAUDE.md rule): a new field touches, in the same change: `backend/app/schemas.py`; the builder in `backend/app/services/predictions.py`; `backend/app/mock_data.py`; `frontend/src/lib/types.ts` (matching nullability exactly); `frontend/src/lib/mock.ts`/`mockCfb.ts`; and an assertion in `frontend/src/lib/__tests__/api.test.ts`. This plan adds `is_neutral_site` to `VenueOut` — all five touch points are covered in Task 4.
- Comments: minimal, clean, simple. Python: SQLAlchemy 2.x typed `Mapped` style, ruff-clean. Schema changes go through Alembic migrations, never manual edits.
- Branch name format: `ct/...`, branched off `main`.
- Production DB: `backend/.env`'s `DATABASE_URL` is the live Railway Postgres the real site reads from. The migration in Task 1 is additive-only (new nullable columns / a new boolean with a server default) — safe to run against production after merge, and Claude will run it directly (per user's go-ahead) rather than leaving it to a separate deploy step.

---

### Task 1: Add `venue_name` / `is_neutral_site` to `Game`, migration

**Files:**
- Modify: `backend/app/models.py` (`Game` class, after `stadium_id`)
- Create: `backend/alembic/versions/<rev>_add_game_venue_fields.py` (via `alembic revision --autogenerate`)

**Interfaces:**
- Produces: `Game.venue_name: str | None`, `Game.is_neutral_site: bool` (default `False`) — consumed by Task 2 (loader), Task 3 (weather refresh), Task 4 (API venue exposure).

- [ ] **Step 1:** Add the two columns to `Game` in `backend/app/models.py`, directly below `stadium_id`:
  ```python
  stadium_id: Mapped[int | None] = mapped_column(ForeignKey("stadiums.stadium_id"))
  # Neutral-site games (nflverse location != "Home") have no Team-derived
  # stadium; venue_name is the raw nflverse venue string so weather/display
  # aren't silently dropped for them.
  venue_name: Mapped[str | None] = mapped_column(String(120))
  is_neutral_site: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
  ```
- [ ] **Step 2:** Generate the migration: `python -m alembic revision --autogenerate -m "add game venue_name and is_neutral_site"`. Open the generated file and confirm it only adds these two nullable/defaulted columns (autogenerate can pick up unrelated drift — trim anything not related to this change).
- [ ] **Step 3:** Apply locally is not possible (no local Postgres running this session — Docker Desktop isn't up); instead validate the migration by reading it and confirming `upgrade()`/`downgrade()` are both correct and reversible. Do not run it against production yet — that happens once after the PR merges (Task 9).
- [ ] **Step 4:** Commit: `git add backend/app/models.py backend/alembic/versions/ && git commit -m "feat(models): add Game.venue_name and Game.is_neutral_site"`.

---

### Task 2: Capture venue/location in the NFL schedule loader

**Files:**
- Modify: `backend/data_pipeline/games_loader.py` (`upsert_games`, around line 82-84)
- Test: `backend/tests/test_games_loader.py`

**Interfaces:**
- Consumes: `Game.venue_name`, `Game.is_neutral_site` from Task 1.
- Produces: every upserted `Game` row has `venue_name` set from nflverse's `stadium` column and `is_neutral_site` set from `location != "Home"`, for both "Home" and "Neutral" rows (harmless to also set it for "Home" rows — keeps the field populated everywhere for future use, e.g. showing the real stadium name for divisional home games too).

- [ ] **Step 1: Write the failing test** — add to `backend/tests/test_games_loader.py`:
  ```python
  def test_neutral_site_game_captures_venue_name_and_flag(db):
      """A neutral-site row (nflverse location='Neutral') must not silently
      drop its venue — stadium_id stays NULL (no home team's stadium
      applies) but the raw venue name and a neutral-site flag are kept."""
      row = _row("2026_01_SF_LA", 2026, 1, "2026-09-10", "20:35", "LA", "SF")
      row["location"] = "Neutral"
      row["stadium"] = "Melbourne Cricket Ground"
      schedules = pd.DataFrame([row])
      upsert_games(db, schedules)
      game = db.query(Game).filter(Game.game_id == "2026_01_SF_LA").one()
      assert game.stadium_id is None
      assert game.venue_name == "Melbourne Cricket Ground"
      assert game.is_neutral_site is True

  def test_home_game_still_gets_venue_name(db):
      """Non-neutral games also get venue_name populated (from the same
      nflverse column), just with is_neutral_site False."""
      row = _row("2026_03_D", 2026, 3, "2026-09-24", "13:00", "KC", "BUF")
      row["stadium"] = "GEHA Field at Arrowhead Stadium"
      schedules = pd.DataFrame([row])
      upsert_games(db, schedules)
      game = db.query(Game).filter(Game.game_id == "2026_03_D").one()
      assert game.is_neutral_site is False
      assert game.venue_name == "GEHA Field at Arrowhead Stadium"
  ```
  Also update the `_row()` helper at the top of the file to accept the new `stadium` key with a default so every existing call site keeps working unmodified:
  ```python
  def _row(game_id, season, week, gameday, gametime, home="KC", away="BUF"):
      return {
          "game_id": game_id, "season": season, "week": week, "gameday": gameday,
          "gametime": gametime, "home_team": home, "away_team": away, "location": "Home",
          "home_score": None, "away_score": None, "div_game": False,
          "spread_line": None, "total_line": None, "home_moneyline": None, "away_moneyline": None,
          "stadium": None,
      }
  ```
- [ ] **Step 2: Run test to verify it fails.** `cd backend && .venv/Scripts/python -m pytest tests/test_games_loader.py -v` — expect `AttributeError`/`AssertionError` since `venue_name`/`is_neutral_site` don't exist yet.
- [ ] **Step 3: Implement.** In `games_loader.py`, replace:
  ```python
  game.stadium_id = (
      stadium_by_team.get(ids[home]) if row.location == "Home" else None
  )
  ```
  with:
  ```python
  is_neutral = row.location != "Home"
  game.stadium_id = None if is_neutral else stadium_by_team.get(ids[home])
  game.is_neutral_site = is_neutral
  game.venue_name = _opt(getattr(row, "stadium", None))
  ```
  (`getattr` with a default keeps this safe if a future data source ever omits the column entirely.)
- [ ] **Step 4: Run tests to verify they pass.** `.venv/Scripts/python -m pytest tests/test_games_loader.py -v` — all green, including the 5 pre-existing tests (regression check).
- [ ] **Step 5: Commit:** `git add backend/data_pipeline/games_loader.py backend/tests/test_games_loader.py && git commit -m "feat(pipeline): capture venue name and neutral-site flag on schedule ingest"`.

---

### Task 3: Fetch weather for neutral-site games by venue name

**Files:**
- Modify: `backend/data_pipeline/refresh_weather.py`
- Test: `backend/tests/test_refresh_weather.py` (new file)

**Interfaces:**
- Consumes: `Game.venue_name`, `Game.is_neutral_site` (Task 1/2), `fetch_day` signature.
- Produces: `fetch_day(location: str, day: str, api_key: str)` — location is now a string (either `"lat,lon"` or a free-text venue name; Visual Crossing's Timeline API accepts both in the same `{location}` path segment). Existing callers updated in the same commit — no other module calls `fetch_day` (verified: only `refresh_weather.py` imports it, per `grep -rn "fetch_day" backend/`; if that has changed, update every call site found).

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_refresh_weather.py`:
  ```python
  """Neutral-site games (no Team-derived stadium) must not be silently
  skipped the same way domes are — they should be fetched by venue name."""
  from unittest.mock import patch

  from data_pipeline.refresh_weather import fetch_day


  def test_fetch_day_accepts_lat_lon_string():
      with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
          mock_get.return_value.json.return_value = {"days": []}
          mock_get.return_value.raise_for_status.return_value = None
          fetch_day("33.9535,-118.3392", "2026-09-10", "key")
          url = mock_get.call_args[0][0]
          assert "33.9535,-118.3392" in url

  def test_fetch_day_accepts_venue_name_string():
      with patch("data_pipeline.refresh_weather.requests.get") as mock_get:
          mock_get.return_value.json.return_value = {"days": []}
          mock_get.return_value.raise_for_status.return_value = None
          fetch_day("Melbourne Cricket Ground", "2026-09-10", "key")
          url = mock_get.call_args[0][0]
          assert "Melbourne Cricket Ground" in url
  ```
- [ ] **Step 2: Run test to verify it fails** (current `fetch_day(lat, lon, day, api_key)` signature takes two positional numbers, not one location string): `.venv/Scripts/python -m pytest tests/test_refresh_weather.py -v` — expect a `TypeError`.
- [ ] **Step 3: Implement.** In `refresh_weather.py`:
  ```python
  def fetch_day(location: str, day: str, api_key: str) -> dict:
      resp = requests.get(
          f"{BASE_URL}/{location}/{day}",
          params={"key": api_key, "unitGroup": "us", "include": "hours"},
          timeout=30,
      )
      resp.raise_for_status()
      return resp.json()
  ```
  and in `main()`'s loop, replace the skip/fetch block:
  ```python
  for game in games:
      stadium = game.stadium
      if stadium is not None and stadium.is_dome:
          skipped += 1
          continue
      if stadium is not None:
          location = f"{stadium.lat},{stadium.lon}"
      elif game.venue_name:
          location = game.venue_name
      else:
          skipped += 1
          continue
      try:
          payload = fetch_day(
              location,
              game.game_date.isoformat(),
              settings.visual_crossing_api_key,
          )
      except requests.RequestException as exc:
          print(f"weather refresh: {game.game_id} failed ({exc})")
          failed += 1
          continue
      ...
  ```
  Update the closing summary line's `"(dome/international)"` text to `"(dome, or no venue known)"` since international games are no longer lumped in when a venue name exists. Update the module docstring's second sentence accordingly (no longer "and no-stadium (international) games are skipped" — say venue-name lookup is attempted for neutral-site games; a true dome or a game with neither a stadium nor a venue name is skipped).
- [ ] **Step 4: Run tests to verify they pass:** `.venv/Scripts/python -m pytest tests/test_refresh_weather.py -v`.
- [ ] **Step 5: Commit:** `git add backend/data_pipeline/refresh_weather.py backend/tests/test_refresh_weather.py && git commit -m "fix(pipeline): fetch weather for neutral-site games by venue name"`.

---

### Task 4: Surface the real venue on the API + matchup page instead of a blank block

**Files:**
- Modify: `backend/app/schemas.py` (`VenueOut`)
- Modify: `backend/app/services/predictions.py` (venue construction, ~line 338-341)
- Modify: `backend/app/mock_data.py` (add `is_neutral_site` to each `"venue"` dict; default `False`)
- Modify: `frontend/src/lib/types.ts` (matching `Venue` type)
- Modify: `frontend/src/lib/mock.ts` and `frontend/src/lib/mockCfb.ts` (matching fixtures)
- Modify: `frontend/src/app/matchup/[gameId]/...` wherever venue is rendered (find via `grep -rn "venue" frontend/src` — add a small "Neutral site" note when `is_neutral_site` is true)
- Test: `backend/tests/test_api.py` (assert new field), `frontend/src/lib/__tests__/api.test.ts` (assert new field per CLAUDE.md's rule)

**Interfaces:**
- Consumes: `Game.venue_name`, `Game.is_neutral_site` (Task 1/2).
- Produces: `VenueOut.is_neutral_site: bool` — new field on the existing `venue` object in `PredictionOut`.

- [ ] **Step 1: Write the failing backend test.** In `backend/tests/test_api.py`, extend (or add near) the existing prediction-endpoint test to assert `body["venue"]["is_neutral_site"] is False` for a normal game, and add a case building a neutral-site game (`is_neutral_site=True`, `stadium_id=None`, `venue_name="Melbourne Cricket Ground"`) asserting `body["venue"] == {"name": "Melbourne Cricket Ground", "city": None, "is_dome": None, "is_neutral_site": True}`.
- [ ] **Step 2: Run it, confirm failure** (field doesn't exist yet): `.venv/Scripts/python -m pytest tests/test_api.py -v`.
- [ ] **Step 3: Implement backend.**
  - `schemas.py`: add `is_neutral_site: bool = False` to `VenueOut`.
  - `predictions.py`: change the `VenueOut(...)` construction to:
    ```python
    venue=VenueOut(
        name=game.stadium.name if game.stadium else game.venue_name,
        city=game.stadium.city if game.stadium else None,
        is_dome=game.stadium.is_dome if game.stadium else None,
        is_neutral_site=game.is_neutral_site,
    ),
    ```
  - `mock_data.py`: add `"is_neutral_site": False` to every existing `"venue"` dict (find all with `grep -n '"venue":' backend/app/mock_data.py`).
- [ ] **Step 4: Run backend tests, confirm pass:** `.venv/Scripts/python -m pytest tests/test_api.py -v`.
- [ ] **Step 5: Frontend contract.** Read `frontend/src/lib/types.ts`'s `Venue` (or equivalent) type and add `is_neutral_site: boolean` matching nullability. Update `frontend/src/lib/mock.ts` and `mockCfb.ts` fixtures to include the field (default `false`, and set `true` on any fixture that represents a neutral-site game if one exists — otherwise just default false everywhere). Add an assertion in `frontend/src/lib/__tests__/api.test.ts` per CLAUDE.md's rule for new API fields.
- [ ] **Step 6: Frontend display.** Find where `venue.name`/`venue.is_dome` currently render on the matchup page (`grep -rn "venue\." frontend/src/app frontend/src/components`) and add: when `venue.is_neutral_site` is true, show a small "Neutral site" label/badge next to the venue name (follow the existing badge/label styling pattern already used elsewhere on that page — do not invent a new visual style).
- [ ] **Step 7: Run frontend tests:** `cd frontend && npm run lint && npx vitest run` (or whatever the existing test command is — check `package.json` `scripts`).
- [ ] **Step 8: Commit:** `git add -A && git commit -m "feat(api): surface real venue name and neutral-site flag on matchup page"`.

---

### Task 5: Fix market-factor direction to reflect real market data, not local SHAP sign

**Files:**
- Modify: `backend/ml/explain.py` (`top_factors`)
- Test: `backend/tests/test_explain.py` (new file)

**Interfaces:**
- Consumes: nothing new — `top_factors(explainer, row, home_win_prob, n, sport)` keeps its exact signature; `row` already carries the raw feature values used to build `x` in `predict_week.py`, so no caller changes needed.
- Produces: same `factors` list shape (`feature`, `label`, `value`, `direction`), but `direction` for `market_spread_home` and `market_home_prob` is now derived from the feature's own raw value, never from the SHAP sign.

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_explain.py`:
  ```python
  """market_spread_home / market_home_prob are checkable facts (which team
  the market favors) — their displayed direction must match the raw value,
  not the model's local SHAP attribution, which can point the other way
  for small/near-toss-up lines (see cfb_401856682, OSU@TEX, Week 2 2026:
  market_spread_home=+1.5 favors the home team, but that feature's SHAP
  contribution was locally negative)."""
  import numpy as np
  import pandas as pd

  from ml.explain import top_factors


  class _FakeExplainer:
      def __init__(self, values):
          self._values = values

      def shap_values(self, row):
          return np.array([self._values])


  def test_market_spread_direction_follows_raw_value_not_shap_sign():
      row = pd.DataFrame([{
          "market_spread_home": 1.5,   # positive = home favored
          "market_home_prob": 0.517,   # >0.5 = home favored
          "elo_diff": -41.1,
      }])
      # SHAP says "away" for both market features (the reproduced real bug);
      # elo_diff SHAP is genuinely negative too and has no ground truth to
      # override, so it must stay "away".
      shap_values = [-0.12, -0.04, -0.02]
      explainer = _FakeExplainer(shap_values)
      factors = top_factors(explainer, row, home_win_prob=0.45, n=3, sport="CFB")
      by_feature = {f["feature"]: f for f in factors}
      assert by_feature["market_spread_home"]["direction"] == "home"
      assert by_feature["market_home_prob"]["direction"] == "home"
      assert by_feature["elo_diff"]["direction"] == "away"

  def test_market_spread_negative_still_favors_away():
      row = pd.DataFrame([{"market_spread_home": -3.0, "market_home_prob": 0.4}])
      shap_values = [0.05, 0.05]  # even if SHAP disagreed, raw value wins
      explainer = _FakeExplainer(shap_values)
      factors = top_factors(explainer, row, home_win_prob=0.4, n=2, sport="NFL")
      by_feature = {f["feature"]: f for f in factors}
      assert by_feature["market_spread_home"]["direction"] == "away"
      assert by_feature["market_home_prob"]["direction"] == "away"
  ```
- [ ] **Step 2: Run test to verify it fails:** `.venv/Scripts/python -m pytest tests/test_explain.py -v` — current code derives direction purely from `value >= 0`, so the first test's `market_spread_home`/`market_home_prob` assertions fail (currently "away").
- [ ] **Step 3: Implement.** In `ml/explain.py`, inside `top_factors`'s loop:
  ```python
  MARKET_GROUND_TRUTH = {
      "market_spread_home": lambda raw: raw > 0,
      "market_home_prob": lambda raw: raw > 0.5,
  }

  for idx in order:
      feature = row.columns[idx]
      value = float(shap_values[idx] * scale)
      if feature in MARKET_GROUND_TRUTH:
          raw = float(row.iloc[0][feature])
          direction = "home" if MARKET_GROUND_TRUTH[feature](raw) else "away"
      else:
          direction = "home" if value >= 0 else "away"
      factors.append(
          {
              "feature": feature,
              "label": labels.get(feature, feature),
              "value": round(value, 4),
              "direction": direction,
          }
      )
  ```
  (Exact-zero/exact-0.5 edge case keeps the current `>=`-style tie-break behavior via the `else` branch's own inherited convention — not expected in practice since a real market line is essentially never exactly pick'em with prob exactly 0.5.)
- [ ] **Step 4: Run tests to verify they pass:** `.venv/Scripts/python -m pytest tests/test_explain.py -v`.
- [ ] **Step 5: Regression-check narrate.py's existing tests still pass** (they consume `factors` shape): `.venv/Scripts/python -m pytest tests/test_narrate.py -v`.
- [ ] **Step 6: Commit:** `git add backend/ml/explain.py backend/tests/test_explain.py && git commit -m "fix(explain): ground market-factor direction in raw data, not local SHAP sign"`.

---

### Task 6: Full backend + frontend test suite and lint

**Files:** none (verification only)

- [ ] **Step 1:** `cd backend && .venv/Scripts/python -m pytest` — full suite green.
- [ ] **Step 2:** `cd backend && .venv/Scripts/python -m ruff check .` — clean.
- [ ] **Step 3:** `cd frontend && npm run lint` — clean.
- [ ] **Step 4:** `cd frontend && npm run build` — succeeds (catches type errors from the `types.ts` change in Task 4).
- [ ] **Step 5:** If anything fails, fix before moving on — do not proceed to docs/version/PR with a red suite.

---

### Task 7: Regenerate the corrected prediction rows in production

**Files:** none (data operation, production DB)

Context: the two bugs fixed above only change *how future/re-run predictions and pipeline refreshes are computed* — they do not retroactively fix rows already sitting in the production DB (the bad OSU@TEX SHAP row, the 8 neutral-site games' missing weather/venue). This task re-runs the affected jobs after the migration lands.

- [ ] **Step 1:** After Task 9's migration is applied to production, re-run the schedule loader so existing games pick up `venue_name`/`is_neutral_site`: `python -m data_pipeline.refresh_schedule` (NFL) — confirm via a read-only query that the 8 previously-null-stadium games now have `venue_name` set.
- [ ] **Step 2:** Re-run weather for the affected window: `python -m data_pipeline.refresh_weather --sport nfl` — confirm `2026_01_SF_LA` now has a `Weather` row (or a clean, logged failure if Visual Crossing can't geocode "Melbourne Cricket Ground", in which case report that back rather than silently leaving it blank).
- [ ] **Step 3:** Re-run CFB Week 2 predictions so the SHAP fix applies to already-generated rows: `python -m app.jobs.predict_week --season 2026 --week 2 --sport cfb`. Confirm `cfb_401856682`'s stored `shap_top_features` now shows `market_spread_home`/`market_home_prob` direction `"home"`.
- [ ] **Step 4:** Spot-check a handful of other CFB Week 2 and NFL Week 1 predictions weren't disturbed in any unexpected way (probabilities unchanged — only `direction` labels and narration wording should differ where the fix applies).

---

### Task 8: Update docs and version numbers

**Files:**
- Modify: `README.md` (if the neutral-site/weather behavior is described inaccurately anywhere)
- Modify: `backend/README.md` (`refresh_weather` row's description: no longer purely "NFL" dome-or-nothing behavior)
- Modify: `DECISIONS.md` (add an entry: why market-factor direction is grounded in raw data instead of SHAP sign; why neutral-site venue capture was added)
- Modify: `CHANGELOG.md`
- Modify: `frontend/package.json` (`version` bump — patch, since these are bug fixes with one small additive UI element, not a breaking/major change)
- Modify: `backend/.env.example` and `MODEL_VERSION`/`MODEL_VERSION_CFB` — **no bump needed**: the model artifacts themselves are unchanged (same weights, same features); only the explainability *display* layer changed. Note this explicitly in `DECISIONS.md` so it isn't second-guessed later.
- Modify: `CLAUDE.md` only if any convention documented there became inaccurate (it currently doesn't mention venue/neutral-site handling at all, so this is likely additive, not corrective — check the "Conventions & constraints" list for anything to add about the market-factor ground-truth rule, since that's a real, non-obvious convention future changes should respect).

- [ ] **Step 1:** Bump `frontend/package.json` `"version"` (e.g. `1.0.3` → `1.0.4`).
- [ ] **Step 2:** Add a `## [1.0.4]` entry to `CHANGELOG.md` describing the three user-visible/behavioral changes (neutral-site venue + weather, market-factor direction fix, and the Wednesday-kickoff investigation closed as not-a-bug).
- [ ] **Step 3:** Add two short entries to `DECISIONS.md`: (a) neutral-site games get their venue captured from nflverse's raw `stadium` field and weather is fetched by venue-name geocoding rather than lat/lon, since no `Stadium` row exists for most international venues; (b) `market_spread_home`/`market_home_prob`'s displayed `direction` is grounded in the raw feature value, not the SHAP sign, because these two features represent an independently checkable fact (which team the market favors) rather than a model inference, and a SHAP-only rendering can mislead near a toss-up line.
- [ ] **Step 4:** Add a short line to CLAUDE.md's "Conventions & constraints" documenting the market-factor ground-truth rule (so a future engineer touching `ml/explain.py` doesn't revert it), and one about `Game.venue_name`/`is_neutral_site` existing for neutral-site games.
- [ ] **Step 5:** Update `backend/README.md`'s `refresh_weather` row/description and any relevant explanatory paragraph to reflect the new venue-name fallback.
- [ ] **Step 6:** Commit: `git add -A && git commit -m "docs: update CHANGELOG, DECISIONS, CLAUDE.md, README, bump version to 1.0.4"`.

---

### Task 9: Push, open PR, wait for CI, merge; apply production migration

**Files:** none (git/GitHub operations)

- [ ] **Step 1:** `git push -u origin ct/week1-checkin-fixes` (branch created in Task 0, before Task 1's first commit — see note below).
- [ ] **Step 2:** Open a PR against `main` (via `gh pr create` or the `pr-manager` agent) with a description summarizing: what was found during the Week 1 check-in, the two real bugs fixed, the one investigated-and-closed (Wednesday kickoff), and the one investigated-but-deferred (503s — needs Railway logs), plus the version bump.
- [ ] **Step 3:** Wait for CI checks to pass (`gh pr checks --watch` or equivalent). If any check fails, fix and push again — do not merge red.
- [ ] **Step 4:** Once green, merge the PR into `main` (squash or merge per repo convention — check existing merged PRs' style with `gh pr list --state merged --limit 5` and match it).
- [ ] **Step 5:** Immediately after merge, run the Task 1 migration against production: `cd backend && .venv/Scripts/python -m alembic upgrade head` (using the existing `backend/.env` `DATABASE_URL`). Confirm with a read-only query that `games.venue_name` and `games.is_neutral_site` now exist.
- [ ] **Step 6:** Run Task 7's data-regeneration steps against production.
- [ ] **Step 7:** Do the extensive Chrome QA pass (Task 10) against the now-live, now-fixed production site.

Note: Task 0 (create the branch) happens before Task 1, not as its own numbered task — see Execution Handoff below.

---

### Task 10: Extensive Chrome QA against the live site post-fix

**Files:** none (manual QA)

- [ ] **Step 1:** Repeat the original site walkthrough checklist (homepage, CFB Week 1 graded games, CFB Week 2 matchups, NFL Week 1 matchups, season-record banner, `/how-it-works`, console/network errors, footer version) end-to-end to confirm nothing regressed.
- [ ] **Step 2:** Specifically verify: `2026_01_SF_LA`'s matchup page now shows a real venue name (with a neutral-site note) instead of a blank venue block, and — if the weather refresh in Task 7 succeeded — real weather instead of nothing.
- [ ] **Step 3:** Specifically verify: the OSU@TEX (`cfb_401856682`) matchup page's narration/factor list no longer states the market favors the team the raw spread/moneyline don't actually favor.
- [ ] **Step 4:** Confirm the footer shows the bumped version number.
- [ ] **Step 5:** Report final findings.

---

## Self-Review

**Spec coverage:** neutral-site weather/venue bug → Tasks 1-4, 7, 10. Market-factor direction bug → Task 5, 7, 10. Wednesday-kickoff → confirmed not a bug, documented in Task 8's CHANGELOG entry, no code task needed. 503 prefetch → explicitly deferred per user's "investigate first" answer; no production log access available this session, documented as a known open item in Task 8/PR description rather than guess-patched. Branch naming, docs/version updates, PR/CI/merge, production migration, extensive Chrome QA, "double check for more bugs" — all covered by their own tasks or by the parallel audit subagent already dispatched.

**Placeholder scan:** no TBD/TODO markers; all code steps show real code.

**Type consistency:** `fetch_day`'s new single-`location`-string signature is used consistently in both its test (Task 3) and its only call site (Task 3, same task). `top_factors`'s signature is unchanged everywhere it's called (`predict_week.py`, `backfill_predictions.py` — verify the latter also calls it with the same shape before merging; if it has its own explain call site, it inherits the fix automatically since the function itself changed, not its callers).
