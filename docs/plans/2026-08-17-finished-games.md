# Finished Games Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use **superpowers:subagent-driven-development** to implement this plan task-by-task. The user has chosen this mode: dispatch a fresh subagent per task and review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop at every 🚦 REVIEW CHECKPOINT** and report to the user before continuing. There are six. They are not optional; the user asked to review between milestones.
>
> **Never commit and never push.** Each task ends with a verification gate instead of a commit. This overrides the commit steps that superpowers skills normally instruct you to perform.

**Goal:** Show completed games with final scores and a correct/incorrect verdict, add a completed/upcoming/all filter, a current-season prediction record against the market baseline, and four launch extras.

**Architecture:** Scores and a server-computed verdict are added to the existing `GameSummary` and `PredictionOut` schemas. Prediction integrity is fixed first so `predicted_at` genuinely means "before kickoff". Walk-forward backtest predictions are persisted under a distinct model version so the UI has content before the season starts, without presenting in-sample results as a live record.

**Tech Stack:** FastAPI, SQLAlchemy 2.x typed `Mapped`, Postgres 16 (tests use in-memory SQLite), pandas, XGBoost, Next.js 16 App Router, TypeScript strict, Tailwind v4, Jest + Testing Library.

**Spec:** `docs/specs/2026-08-17-finished-games-design.md`. Read it before starting. This plan argues from that spec; both travel together.

## Context for a fresh session

You have no history with this repo. Everything below was learned the hard way in
a prior session and is not obvious from the code.

### Where things stand

- Branch: `ct/chore/release-preparation`. **There is substantial uncommitted work
  already in the tree** (~60 files) from a release-prep pass. Do not `git stash`,
  `git checkout .`, or `git reset`. The user reviews before anything is committed.
- Baseline test counts before you start: **backend 101, frontend 52**. Both green,
  `ruff` and ESLint clean, production build passes. If your first run shows fewer,
  something is wrong with your environment, not the repo.
- App is v1.0.0. Models were retrained and stamped `1.0.0` / `cfb-1.0.0`, and
  `ml/reports/backtest.md` + `backtest_cfb.md` were regenerated from those runs.

### Environment

Windows. Both PowerShell and Git Bash are available and take different syntax.

```
backend python:  backend/.venv/Scripts/python      (Windows layout, not bin/)
postgres:        docker start blitzcast-postgres    (port 5432)
backend API:     .venv/Scripts/python -m uvicorn app.main:app --port 8000
frontend:        cd frontend && npm run dev         (port 3000)
```

- **Docker Desktop is often not running.** `docker start` fails with a
  `dockerDesktopLinuxEngine` pipe error when it is down. You cannot launch it
  yourself; ask the user.
- PowerShell has no `wc`, `grep`, `head`, or `tail`. Use `Select-Object -Last N`
  or switch to the Bash tool.
- Reading or grepping anything matching `.env` is blocked by a safety guard, even
  `.env.example`. Use the Read tool for `.env.example`; for `backend/.env`, ask
  the user to make changes.
- `backend/.env` pins `MODEL_VERSION=1.0.0`. **A value in `.env` overrides the
  default in `app/config.py`.** A prior session bumped the config default, retrained,
  and silently got an artifact named for the old version because `.env` won. If a
  retrain writes an unexpected filename, check `.env` first.

### Gotchas that will cost you an hour each

1. **Next caches mock-mode 404s.** After switching `NEXT_PUBLIC_USE_MOCK` from 1
   to 0, real games 404 until you `rm -rf frontend/.next` and restart. The dev
   server log will show a 200 from the backend and a 404 from the page. This is
   not a code bug; it burned a prior session.
2. **Tests run on in-memory SQLite** (`backend/tests/conftest.py`), production is
   Postgres 16. `DISTINCT ON` and other Postgres-only syntax will pass in prod and
   fail in tests. Keep queries portable.
3. **`nflreadpy` rejects future seasons.** `load_pbp([2026])` raises
   `ValueError: Season must be between 1999 and 2025` until the season starts.
   `refresh_stats.py` already guards this; anything new touching pbp needs the
   same treatment.
4. **The Chrome MCP renderer times out intermittently.** `Page.captureScreenshot`
   fails after 30s roughly one call in ten. Just retry; the page is fine.
5. **`frontend/.env.local` exists and is gitignored.** Do not read it, do not
   commit it. It already sets `NEXT_PUBLIC_USE_MOCK=0` and points at
   `localhost:8000`.

### Data facts as of 2026-08-17

- **The 2026 season has not started.** NFL week 1 runs Sep 9-14 (the opener is
  Wednesday Sep 9, not the traditional Thursday; that is real, not a bug).
- **Zero games have both a final score and a prediction.** 6,020 finished games
  exist across 2021-2025, but predictions only cover 2026 week 1, which is
  unplayed. This is exactly why Milestone 3 (backfill) must precede any UI work,
  and why you will have nothing to look at until it runs.
- `Game.status` holds only `"scheduled"` (1,161) and `"final"` (6,020). It is
  maintained, but derived and unindexed. The plan keys off scores instead; see
  Global Constraints.
- 2026 NFL has 272 games / 16 in week 1. 2026 CFB has 888 games / 99 in week 1.
- Only 6 CFB games currently carry live odds rows. Most CFB games have no market
  features until lines post, which is expected; XGBoost handles the nulls.

### Recently fixed bugs. Do not regress these.

A prior session found and fixed each of these. They are subtle and a careless
edit will reintroduce them.

1. **Spread sign convention.** The Odds API quotes negative when home is favored;
   nflverse quotes positive. Both write `spread_home`, so ingestion normalizes to
   **positive = home favored** (`data_pipeline/refresh_odds.py:book_spread_to_home`).
   `frontend/src/lib/format.ts:fmtSpread` assumes that convention. Pinned by
   `backend/tests/test_odds.py` and the `fmtSpread` tests. If you touch odds or
   spread display, run those first.
2. **`_prediction_probs` ordering** (`services/predictions.py`). It is scoped by
   season/sport/week and ordered ascending by `predicted_at` so the newest row
   wins, deliberately matching `get_prediction_detail`. Multiple prediction rows
   per game are normal now (a version bump creates them). Do not "simplify" the
   ordering away or the slate and the detail page will silently disagree.
3. **`prediction_status` is `"ready"`, not `"available"`.** The backend once
   returned `"available"` while the frontend only recognized `"ready"`, so every
   completed prediction rendered as pending site-wide.
4. **Rams are keyed `"LA"` internally, displayed as `"LAR"`.** nflverse uses `LA`;
   game IDs, routes, and lookups all use it. `displayAbbr()` in
   `frontend/src/lib/teams.ts` swaps it for display only, and **only for NFL**.
   CFB passes its own abbreviations through untouched. The pattern in the codebase
   is `cfb ? team.abbr : displayAbbr(team.abbr)`. Chargers stay `LAC`.
5. **`Venue`, `Odds`, and `Weather` members are all individually nullable.**
   Neutral-site games have a null venue name; a game can have a spread but no
   moneyline. Guard per field, not just on the container object, or the UI renders
   the literal string `null`.

### Contract drift is this repo's recurring failure mode

Three separate bugs have shipped from `frontend/src/lib/types.ts` disagreeing
with `backend/app/schemas.py` about nullability or enum values. When you add a
field, change **all five** places in the same task:

1. `backend/app/schemas.py`
2. `backend/app/services/predictions.py` (the builder that populates it)
3. `backend/app/mock_data.py` (mock mode diverges silently otherwise)
4. `frontend/src/lib/types.ts` (match nullability *exactly*)
5. `frontend/src/lib/mock.ts` and `mockCfb.ts`

Then assert it in `frontend/src/lib/__tests__/api.test.ts`.

### Voice and copy

The site speaks like an ESPN or College GameDay broadcast: upbeat, real football
vocabulary, contractions, some humor. Existing copy worth matching: "Delay of
game", "Flag on the play", "We can't reach the press box", "From the booth",
"Every matchup, called before kickoff".

**No em dashes anywhere a user can see.** A prior pass removed them from titles,
meta descriptions, empty states, and ~21 mock narratives, rewrote the narration
system prompt, and added a deterministic sanitizer
(`backend/app/services/narrate.py:_plain_punctuation`) because roughly 90% of
generated narrations contained one. Do not reintroduce them in new copy.

### Honesty constraints, non-negotiable

The model **does not beat Vegas**. It trails by about 3 points of accuracy
(NFL 0.650 vs 0.682, CFB 0.717 vs 0.738 over the walk-forward backtest). The
README says so plainly, and a prior session corrected it after finding it
overstated. Two consequences for this work:

- Backfilled predictions are reconstructed from a walk-forward backtest, not live
  pre-game calls. They must be **labeled** as such (Task 7 Step 7).
- The record must **never** display the model's accuracy without the market
  baseline beside it (Task 13 Step 3).

Both are easy to drop under implementation pressure. They are requirements.

## Global Constraints

- **Do not commit. Do not push.** Every task ends with a verification gate, not a commit. All work stays in the working tree.
- Ships as **v1.0.0**. No app version bump, no model version bump. `MODEL_VERSION=1.0.0`, `MODEL_VERSION_CFB=cfb-1.0.0`.
- **Leakage rule:** every feature for game G uses only data from strictly before G's kickoff. Tests enforce it. Keep it that way.
- **LLM boundary:** Claude narrates model output only. It never predicts and never alters probabilities.
- **Branding:** "Paymon" / "Paymon Software" only. Never the maintainer's real name in code, comments, or docs.
- **No em dashes** (—) or en dashes (–) in user-visible copy, narration prompts, or docs prose.
- **Completion invariant:** a game is final when `home_score IS NOT NULL AND away_score IS NOT NULL`. Never key off `Game.status`.
- Comments minimal, clean, simple. `ruff check .` clean, `npm run lint` clean.
- Tests run on in-memory SQLite. Keep queries portable; no `DISTINCT ON`.
- Every schema field added must also be added to `backend/app/mock_data.py` and `frontend/src/lib/mock.ts` + `mockCfb.ts`.

## Verification gate (used at the end of every task)

```bash
cd backend  && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check .
cd frontend && npm test && npm run lint && npm run build
```

Both must be green before moving on. Do not commit.

---

# Milestone 1: Prediction integrity

Spec §7.1. **Must land first.** Everything downstream displays a `predicted_at`
that must mean "before kickoff", and today the weekly pipeline overwrites it
after results are known.

### Task 1: Stop re-predicting finished games

**Files:**
- Modify: `backend/app/jobs/predict_week.py:112-145`
- Test: `backend/tests/test_predict_week.py`

**Interfaces:**
- Consumes: `default_week(db, season, sport) -> int | None` (`predict_week.py:25`)
- Produces: no signature change; `main()` behavior change only

- [ ] **Step 1: Write the failing test**

```python
def test_unplayed_game_ids_excludes_finished_games(db):
    """A finished game must not be re-predicted; that would overwrite the
    pre-game call and restamp predicted_at after the result was known."""
    from app.jobs.predict_week import unplayed_game_ids
    from app.models import SPORT_NFL, Game

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    week = game.week
    assert "2026_01_BUF_KC" in unplayed_game_ids(db, 2026, week, SPORT_NFL)

    game.home_score, game.away_score = 27, 24
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(db, 2026, week, SPORT_NFL)


def test_unplayed_game_ids_excludes_a_half_scored_row(db):
    """One score present means the game started; do not predict it."""
    from app.jobs.predict_week import unplayed_game_ids
    from app.models import SPORT_NFL, Game

    game = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    game.home_score, game.away_score = 27, None
    db.commit()
    assert "2026_01_BUF_KC" not in unplayed_game_ids(db, 2026, game.week, SPORT_NFL)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_predict_week.py -k unplayed_game_ids -v`
Expected: FAIL with `ImportError: cannot import name 'unplayed_game_ids'`

- [ ] **Step 3: Add the helper**

**Verified:** `build_features` does **not** return `home_score` / `away_score`.
They are loaded internally by `_load_frames` but dropped before the frame is
returned. Do not try to filter the features frame on them; query the DB instead.
`main()` already holds an open session.

In `backend/app/jobs/predict_week.py`, above `main()`:

```python
def unplayed_game_ids(db: Session, season: int, week: int, sport: str) -> set[str]:
    """Game ids in the week with no score yet. Both scores must be absent: a
    row with one side scored has started, and re-predicting it would restamp
    predicted_at after the result was known."""
    rows = db.scalars(
        select(Game.game_id).where(
            Game.season == season,
            Game.sport == sport,
            Game.week == week,
            Game.home_score.is_(None),
            Game.away_score.is_(None),
        )
    )
    return set(rows)
```

- [ ] **Step 4: Wire it into `main()`**

In `main()`, immediately after `target = features[features["week"] == week]`
(`predict_week.py:119`):

```python
        target = features[features["week"] == week]
        playable = unplayed_game_ids(db, args.season, week, sport)
        skipped = len(target) - target["game_id"].isin(playable).sum()
        target = target[target["game_id"].isin(playable)]
        if skipped:
            print(f"skipping {skipped} already-final {sport} games")
        if target.empty:
            print(f"no unplayed {sport} games found for {args.season} week {week}")
            return
```

`game_id` is confirmed present on the features frame.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_predict_week.py -v`
Expected: PASS, and all pre-existing tests in that file still pass.

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

### Task 2: Stop `default_week` sticking on an unscored game

**Files:**
- Modify: `backend/app/jobs/predict_week.py:25-35`
- Test: `backend/tests/test_predict_week.py`

**Interfaces:**
- Produces: `default_week(db, season, sport) -> int | None`, same signature, new rule

**Problem:** the current query returns the earliest week containing any game with
`home_score IS NULL`. A cancelled game or an unresolved CFB row pins that week
forever, so every weekly run re-predicts an old slate.

**Rule:** return the earliest week that has an unplayed game **and** whose games
are not all in the past. A week whose latest kickoff is more than 36 hours ago is
considered done regardless of missing scores.

- [ ] **Step 1: Write the failing test**

```python
def test_default_week_skips_a_stale_week_with_a_permanently_unscored_game(db):
    """A cancelled week 1 game must not pin default_week to week 1 forever."""
    from app.jobs.predict_week import default_week

    wk1 = db.scalar(select(Game).where(Game.game_id == "2026_01_BUF_KC"))
    wk1.home_score = None          # never resolved
    wk1.away_score = None
    wk1.kickoff_time = datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
    db.commit()

    now = datetime(2026, 10, 1, tzinfo=UTC)   # weeks later
    assert default_week(db, 2026, SPORT_NFL, now=now) != 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_predict_week.py::test_default_week_skips_a_stale_week_with_a_permanently_unscored_game -v`
Expected: FAIL, either `TypeError` on the `now` kwarg, or the assertion fails returning 1.

- [ ] **Step 3: Implement**

```python
STALE_AFTER = timedelta(hours=36)


def default_week(
    db: Session, season: int, sport: str = SPORT_NFL, now: datetime | None = None
) -> int | None:
    """Earliest week that still has a game to play.

    A week whose last kickoff is well past is treated as done even if a game
    never received a score, so a cancellation cannot pin the job forever."""
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(Game.week, func.max(func.coalesce(Game.kickoff_time, Game.game_date)))
        .where(
            Game.season == season,
            Game.sport == sport,
            Game.home_score.is_(None),
        )
        .group_by(Game.week)
        .order_by(Game.week)
    ).all()
    for week, last_kickoff in rows:
        if last_kickoff is None:
            return week
        if _as_utc(last_kickoff) + STALE_AFTER > now:
            return week
    return None
```

Add the coercion helper next to it, because SQLite returns naive datetimes while
Postgres returns aware ones:

```python
def _as_utc(value) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.combine(value, time.min)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
```

Add `from datetime import time, timedelta` and `from sqlalchemy import func` to
the imports.

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_predict_week.py -v`
Expected: PASS, including the pre-existing
`test_default_week_is_sport_scoped` and `test_null_kickoff_game_still_selected`.
If `test_null_kickoff_game_still_selected` breaks, the `last_kickoff is None`
branch is wrong; fix that branch, not the test.

- [ ] **Step 5: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 1

Stop. Report to the user:
- Both integrity fixes landed, tests green.
- Confirm `predict_week` now skips final games and `default_week` cannot stick.

Do not proceed until the user says go.

---

# Milestone 2: API contract

Spec §6.1, §6.2. Unblocks all frontend work.

### Task 3: Scores and verdict on both schemas

**Files:**
- Modify: `backend/app/schemas.py:30-40` and `:90-107`
- Modify: `backend/app/services/predictions.py:116-127` and `:266-303`
- Modify: `backend/app/mock_data.py` (`_summary` ~`:258-269`, prediction builder ~`:320-340`, `_MOCK_GAMES`, `_MOCK_CFB_GAMES`)
- Test: `backend/tests/test_api.py`, new `backend/tests/test_verdict.py`

**Interfaces:**
- Produces: `prediction_verdict(home_win_prob: float | None, home_score: int | None, away_score: int | None) -> bool | None`, importable from `app.services.predictions`
- Produces: `GameSummary.home_score`, `.away_score`, `.prediction_correct`; `PredictionOut.home_score`, `.away_score`, `.prediction_correct`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_verdict.py`:

```python
"""Verdict rule. Three distinct null cases, all real."""

import pytest

from app.services.predictions import prediction_verdict


@pytest.mark.parametrize(
    "prob, home, away, expected",
    [
        (0.62, 27, 24, True),    # favored home won
        (0.62, 24, 27, False),   # favored home lost
        (0.38, 24, 27, True),    # favored away won
        (0.38, 27, 24, False),   # favored away lost
        (None, 27, 24, None),    # no prediction
        (0.62, 24, 24, None),    # tie
        (0.5, 27, 24, None),     # no pick
        (0.62, None, None, None),  # not played
        (0.62, 27, None, None),    # half-scored row is not final
    ],
)
def test_prediction_verdict(prob, home, away, expected):
    assert prediction_verdict(prob, home, away) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_verdict.py -v`
Expected: FAIL with `ImportError: cannot import name 'prediction_verdict'`

- [ ] **Step 3: Implement the rule**

In `backend/app/services/predictions.py`, above `_game_summary`:

```python
def prediction_verdict(
    home_win_prob: float | None, home_score: int | None, away_score: int | None
) -> bool | None:
    """Did the model pick the winner? None when there is nothing to grade:
    no prediction, an unfinished game, a tie, or an exact coin flip."""
    if home_win_prob is None or home_score is None or away_score is None:
        return None
    if home_score == away_score or home_win_prob == 0.5:
        return None
    return (home_win_prob > 0.5) == (home_score > away_score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_verdict.py -v`
Expected: PASS (9 cases)

- [ ] **Step 5: Add the schema fields**

`backend/app/schemas.py`, in `GameSummary` after `home_win_prob`:

```python
    home_score: int | None = None
    away_score: int | None = None
    prediction_correct: bool | None = None
```

In `PredictionOut` after `prediction_status`:

```python
    home_score: int | None = None
    away_score: int | None = None
    prediction_correct: bool | None = None
```

- [ ] **Step 6: Populate them**

`services/predictions.py`, in `_game_summary`, add to the `GameSummary(...)` call:

```python
        home_score=game.home_score,
        away_score=game.away_score,
        prediction_correct=prediction_verdict(
            home_win_prob, game.home_score, game.away_score
        ),
```

In `get_prediction_detail`, add the same three to the `PredictionOut(...)` call,
using `game.home_score`, `game.away_score`, and
`prediction.home_win_prob if prediction else None` for the probability.

- [ ] **Step 7: Mock parity**

In `backend/app/mock_data.py`: add `home_score` / `away_score` keys to at least
two entries in `_MOCK_GAMES` and two in `_MOCK_CFB_GAMES` (one where the model
was right, one where it was wrong), default the rest to `None`, and populate all
three new fields in both `_summary` and the prediction builder using the same
`prediction_verdict` helper. Do not duplicate the rule.

- [ ] **Step 8: Contract test**

Add to `backend/tests/test_api.py`:

```python
def test_game_summary_exposes_scores_and_verdict(client):
    body = client.get("/api/games?week=1&season=2026").json()
    assert body, "expected week 1 games"
    for g in body:
        assert "home_score" in g and "away_score" in g
        assert "prediction_correct" in g


def test_prediction_detail_exposes_scores_and_verdict(client):
    body = client.get("/api/predictions/2026_01_BUF_KC").json()
    assert "home_score" in body and "away_score" in body
    assert "prediction_correct" in body
```

- [ ] **Step 9: Verification gate**

Run the gate. Do not commit.

---

### Task 4: Mirror the contract on the frontend

**Files:**
- Modify: `frontend/src/lib/types.ts:27-39` and `:94-112`
- Modify: `frontend/src/lib/mock.ts`, `frontend/src/lib/mockCfb.ts`
- Test: `frontend/src/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: the three fields from Task 3
- Produces: `GameSummary.home_score`, `.away_score`, `.prediction_correct`; same on `MatchupDetail`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/lib/__tests__/api.test.ts` inside `describe("Contract Validation")`:

```ts
test("GameSummary carries scores and verdict", async () => {
  process.env.NEXT_PUBLIC_USE_MOCK = "1";
  const { getGames } = await import("../api");
  const games = await getGames(1, 2026, "NFL");
  for (const g of games) {
    expect(g).toHaveProperty("home_score");
    expect(g).toHaveProperty("away_score");
    expect(g).toHaveProperty("prediction_correct");
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- api.test`
Expected: FAIL on the missing properties.

- [ ] **Step 3: Add the types**

`frontend/src/lib/types.ts`, in `GameSummary` and `MatchupDetail`:

```ts
  home_score: number | null;
  away_score: number | null;
  prediction_correct: boolean | null;
```

Nullable, matching the backend. This repo has shipped three contract-drift bugs
from guessing nullability; match `schemas.py` exactly.

- [ ] **Step 4: Update the fixtures**

In `mock.ts` and `mockCfb.ts`, add the three fields everywhere a `GameSummary` or
`MatchupDetail` is constructed. Give at least two NFL and two CFB fixtures real
scores, one with a correct verdict and one incorrect, so the UI work in
Milestone 4 has something to render.

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 2

Stop. Report the new contract and confirm mock parity on both sides.

---

# Milestone 3: Backfill

Spec §7.3. Until this runs there are **zero** games with both a score and a
prediction, so none of the UI can be seen or tested.

### Task 5: Persist walk-forward predictions

**Files:**
- Create: `backend/app/jobs/backfill_predictions.py`
- Create: `backend/tests/test_backfill_predictions.py`
- Modify: `backend/README.md` (commands table)

**Interfaces:**
- Consumes: `training_frame(db, seasons, sport)` (`ml/features.py`), `fit_model(train_df, calib_df, calib_fit_df)` and `predict_calibrated(model, calibrator, df)` (`ml/train.py`), `fbs_vs_fbs(df)` (`ml/train.py:47`)
- Produces: `backfill_version(sport: str) -> str` returning `"backtest-1.0.0"` / `"backtest-cfb-1.0.0"`
- Produces: `walk_forward_predictions(df, holdout_seasons, is_cfb) -> pd.DataFrame` with columns `game_id`, `season`, `home_win_prob`

**Why walk-forward and not the shipped model:** the shipped artifact trained on
2022-2025. Scoring those same seasons with it is in-sample and would overstate
accuracy. `ml/backtest.py:118-133` already does the correct thing; reuse that
loop.

- [ ] **Step 1: Write the failing test**

```python
"""Backfilled predictions are labeled and never pollute the live record."""

from app.jobs.backfill_predictions import backfill_version


def test_backfill_version_is_distinct_per_sport():
    assert backfill_version("NFL") == "backtest-1.0.0"
    assert backfill_version("CFB") == "backtest-cfb-1.0.0"


def test_backfill_version_never_collides_with_live_versions():
    """The record query excludes anything starting with 'backtest'."""
    for sport in ("NFL", "CFB"):
        assert backfill_version(sport).startswith("backtest")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_backfill_predictions.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the job**

Create `backend/app/jobs/backfill_predictions.py`:

```python
"""Persist walk-forward predictions for completed seasons.

Each holdout season is scored by a model trained only on strictly prior
seasons, mirroring ml/backtest.py. The shipped artifact must not be used: it
trained on these seasons, so its accuracy on them would be in-sample.

Rows are stamped with a distinct model version so they are excluded from the
live record and can be labeled in the UI as reconstructed.

Usage: python -m app.jobs.backfill_predictions [--sport nfl|cfb]
"""

import argparse
from datetime import timedelta

import pandas as pd
from sqlalchemy import select

from app.db import session_scope
from app.models import SPORT_CFB, SPORT_NFL, Game, Prediction
from ml.backtest import SPORT_BACKTEST
from ml.features import training_frame
from ml.train import fbs_vs_fbs, fit_model, predict_calibrated


def backfill_version(sport: str) -> str:
    return "backtest-cfb-1.0.0" if sport.upper() == "CFB" else "backtest-1.0.0"


def walk_forward_predictions(
    df: pd.DataFrame, holdout_seasons: list[int], is_cfb: bool
) -> pd.DataFrame:
    """One row per scored game, from a model that never saw that season."""
    out = []
    for season in holdout_seasons:
        history = df[df["season"] < season]
        if history.empty:
            continue
        calib_season = int(history["season"].max())
        train_df = history[history["season"] < calib_season]
        calib_df = history[history["season"] == calib_season]
        if train_df.empty:
            continue
        calib_fit_df = calib_df[fbs_vs_fbs(calib_df)] if is_cfb else None
        model, calibrator = fit_model(train_df, calib_df, calib_fit_df)

        holdout = df[df["season"] == season]
        probs = predict_calibrated(model, calibrator, holdout)
        out.append(
            pd.DataFrame(
                {
                    "game_id": holdout["game_id"].to_numpy(),
                    "season": season,
                    "home_win_prob": probs,
                }
            )
        )
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
```

- [ ] **Step 4: Add the persistence half**

Append to the same file:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["nfl", "cfb"], default="nfl")
    args = parser.parse_args()
    sport = SPORT_CFB if args.sport == "cfb" else SPORT_NFL
    cfg = SPORT_BACKTEST[sport]
    version = backfill_version(sport)
    holdout = cfg["holdout_seasons"]

    with session_scope() as db:
        df = training_frame(
            db, list(range(cfg["first_season"], holdout[-1] + 1)), sport=sport
        )
        preds = walk_forward_predictions(df, holdout, sport == SPORT_CFB)
        if preds.empty:
            print(f"backfill ({args.sport}): nothing to write")
            return

        kickoffs = {
            g.game_id: (g.kickoff_time or g.game_date)
            for g in db.scalars(select(Game).where(Game.sport == sport))
        }
        existing = {
            p.game_id: p
            for p in db.scalars(
                select(Prediction).where(Prediction.model_version == version)
            )
        }
        written = 0
        for row in preds.itertuples(index=False):
            kickoff = kickoffs.get(row.game_id)
            if kickoff is None:
                continue
            pred = existing.get(row.game_id)
            if pred is None:
                pred = Prediction(game_id=row.game_id, model_version=version)
                db.add(pred)
                existing[row.game_id] = pred
            pred.home_win_prob = round(float(row.home_win_prob), 4)
            pred.shap_top_features = []
            pred.llm_narrative = None
            # Distinct, pre-kickoff timestamps: ties would make the
            # "latest prediction" ordering nondeterministic.
            pred.predicted_at = _as_utc(kickoff) - timedelta(hours=1)
            written += 1
        db.commit()

    print(f"backfill ({args.sport}): wrote {written} predictions as {version}")


if __name__ == "__main__":
    main()
```

Reuse the `_as_utc` helper from Task 2 by importing it, or duplicate the three
lines if the import would be circular.

**Verified against `ml/backtest.py`:** the config is `SPORT_BACKTEST[sport]`, a
dict keyed by the sport constant, with keys `first_season`, `holdout_seasons`,
and `week_split`. NFL holdout is `[2023, 2024, 2025]` from `FIRST_SEASON = 2022`;
CFB is the same seasons from `first_season: 2022`. There are no `NFL_CONFIG` or
`CFB_CONFIG` names.

**Also verified:** `fit_model`, `predict_calibrated`, and `fbs_vs_fbs` are all
importable from `ml.train`, and `training_frame` returns `game_id`, `season`,
`week`, `home_win`, `kickoff`, and `market_home_prob`.

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_backfill_predictions.py -v`
Expected: PASS

- [ ] **Step 6: Run it for real, both sports**

```bash
cd backend
.venv/Scripts/python -m app.jobs.backfill_predictions --sport nfl
.venv/Scripts/python -m app.jobs.backfill_predictions --sport cfb
```

Then confirm the data exists and the verdicts look sane:

```bash
.venv/Scripts/python -c "
from app.db import session_scope
from app.models import Game, Prediction
from app.services.predictions import prediction_verdict
from sqlalchemy import select
with session_scope() as db:
    rows = db.execute(
        select(Game.sport, Prediction.home_win_prob, Game.home_score, Game.away_score)
        .join(Prediction, Prediction.game_id == Game.game_id)
        .where(Prediction.model_version.like('backtest%'))
    ).all()
    for sport in ('NFL','CFB'):
        v = [prediction_verdict(p,h,a) for s,p,h,a in rows if s==sport]
        graded = [x for x in v if x is not None]
        print(sport, 'graded', len(graded), 'correct', sum(graded),
              f'{sum(graded)/max(len(graded),1):.1%}')
"
```

Expected: NFL accuracy near 0.650 and CFB near 0.717, matching
`backend/ml/reports/backtest.md` and `backtest_cfb.md`. **If NFL comes back near
0.75 or higher, the shipped model leaked into the loop. Stop and fix it.** That
number is the tripwire for the single most important correctness property of
this task.

- [ ] **Step 7: Document the command**

Add to the `backend/README.md` commands table:

```
| Backfill walk-forward predictions | `python -m app.jobs.backfill_predictions --sport nfl\|cfb` |
```

- [ ] **Step 8: Verification gate**

Run the gate. Do not commit.

---

# Milestone 4: Finished-game UI

Spec §8. First visible result.

### Task 6: Verdict badge and score on the game card

**Files:**
- Modify: `frontend/src/components/GameCard.tsx`
- Modify: `frontend/src/app/globals.css` (three theme blocks plus `@theme inline`)
- Test: `frontend/src/components/__tests__/GameCard.test.tsx`

**Interfaces:**
- Consumes: `GameSummary.home_score`, `.away_score`, `.prediction_correct` (Task 4)

**All four states must render** (spec §8):

| Scores | Prediction | Render |
|---|---|---|
| no | no | pending strip, "Prediction pending" |
| no | yes | current predicted state |
| yes | yes | score + verdict badge |
| yes | no | score, **no** verdict badge |

- [ ] **Step 1: Write the failing tests**

```tsx
const finalGame = (correct: boolean | null) => ({
  ...baseGame,
  home_score: 27,
  away_score: 24,
  home_win_prob: correct === false ? 0.38 : 0.62,
  prediction_correct: correct,
});

test("final game shows both scores", () => {
  render(<GameCard game={finalGame(true)} />);
  expect(screen.getByText("27")).toBeInTheDocument();
  expect(screen.getByText("24")).toBeInTheDocument();
});

test("correct prediction shows a called-it badge", () => {
  render(<GameCard game={finalGame(true)} />);
  expect(screen.getByText(/called it/i)).toBeInTheDocument();
});

test("incorrect prediction shows a missed badge", () => {
  render(<GameCard game={finalGame(false)} />);
  expect(screen.getByText(/missed/i)).toBeInTheDocument();
});

test("final game with no prediction shows score but no verdict", () => {
  render(<GameCard game={{ ...finalGame(null), home_win_prob: undefined }} />);
  expect(screen.getByText("27")).toBeInTheDocument();
  expect(screen.queryByText(/called it|missed/i)).not.toBeInTheDocument();
});

test("verdict is not conveyed by color alone", () => {
  render(<GameCard game={finalGame(true)} />);
  // A screen reader user must get the verdict as text.
  expect(screen.getByText(/called it/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- GameCard`
Expected: FAIL on the missing score and badge text.

- [ ] **Step 3: Add verdict color tokens**

`frontend/src/app/globals.css`. Add to **all three** blocks: `:root` (light),
`:root[data-theme="dark"]`, and `:root:not([data-theme="light"])` under
`prefers-color-scheme: dark`. Then map them in `@theme inline`.

```css
  /* Verdict. Paired on-surface and on-turf variants, as gold-text/gold-turf
     are paired. The brand is green, so "correct" leans blue-teal to read as a
     verdict rather than chrome. */
  --verdict-hit: #1d6f5c;
  --verdict-hit-turf: #7fd4b8;
  --verdict-miss: #a33a3a;
  --verdict-miss-turf: #f0a3a3;
```

Pick dark-theme values with AA contrast at `text-[9px]`. Both verdicts must
differ in **luminance**, not just hue: red and green is the worst possible pair
for deuteranopia and protanopia, which is why the text label carries the meaning.

- [ ] **Step 4: Implement in `GameCard.tsx`**

Derive the state near the top of the component:

```tsx
  const final = game.home_score != null && game.away_score != null;
  const verdict = game.prediction_correct;
```

In `TeamRow`, when `final`, render the score in the existing `ml-auto` slot
(`GameCard.tsx:38-46`) instead of the percentage, giving the winner the emphasis
currently given to `favored`.

In the meta row's `ml-auto` slot (`:111-117`), add a branch before the existing
two, styled like the Prime-time pill (`:107`):

```tsx
        {verdict !== null && verdict !== undefined ? (
          <span
            className={`ml-auto rounded-sm border px-1.5 py-0.5 text-[9px] tracking-[0.15em] ${
              verdict
                ? "border-verdict-hit/50 text-verdict-hit"
                : "border-verdict-miss/50 text-verdict-miss"
            }`}
          >
            {verdict ? "Called it" : "Missed"}
          </span>
        ) : null}
```

Replace the win-prob bar with a "FINAL" treatment when `final`, mirroring the
existing pending-hatch branch (`:96-98`).

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test -- GameCard`
Expected: PASS, including all pre-existing GameCard tests.

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

### Task 7: Final state on the matchup page

**Files:**
- Modify: `frontend/src/components/MatchupHero.tsx`
- Modify: `frontend/src/components/StatTicker.tsx`
- Modify: `frontend/src/components/ReasoningPanel.tsx`

**Interfaces:**
- Consumes: `MatchupDetail.home_score`, `.away_score`, `.prediction_correct`

- [ ] **Step 1: Derive the state**

In `MatchupHero.tsx`, next to the existing `pending` (`:69`):

```tsx
  const final = m.home_score != null && m.away_score != null;
```

Same derivation in `ReasoningPanel.tsx` next to its `pending` (`:17`).

- [ ] **Step 2: Score in the hero**

`TeamColumn` (`MatchupHero.tsx:49-62`) already renders a large `font-display`
number with a caption. When `final`, render the score there with a `Final`
caption. Pass `final` and the team's score into `TeamColumn` as props.

- [ ] **Step 3: Verdict band**

The hero's bottom band (`:102-131`) is already a state ternary. Add a `final`
branch showing "Model called it" or "Model missed". Use the `-turf` token
variants; this sits on the turf gradient, not `--surface`.

- [ ] **Step 4: Final pill in the meta line**

Add `{final ? <Badge>Final</Badge> : null}` to the meta row (`:76-88`), reusing
the existing `Badge` component (`:8-14`).

- [ ] **Step 5: Result cell in StatTicker**

`StatTicker.tsx:49-56` builds a `[label, value][]` array. When final, add:

```tsx
    ["Final", `${abbr(m.away.abbr)} ${m.away_score} / ${abbr(m.home.abbr)} ${m.home_score}`],
```

Use the existing `abbr()` helper so LAR/LAC display stays correct.

- [ ] **Step 6: Verdict copy in ReasoningPanel**

`ReasoningPanel.tsx:18` already computes `favored`, the model's pick. Above the
narrative (`:37-43`), when final, add one plain sentence stating the pick and
whether it landed. No em dashes.

- [ ] **Step 7: Label reconstructed predictions**

If `m.model_version?.startsWith("backtest")`, add a short note that this
prediction was reconstructed from a walk-forward backtest rather than made live
before kickoff. **This is a spec requirement (§7.3), not optional.** Presenting
reconstructed predictions as live pre-game calls would be dishonest.

- [ ] **Step 8: Verification gate**

Run the gate. Do not commit.

---

### Task 8: Chrome verification of the finished-game UI

**Files:** none. Verification only.

- [ ] **Step 1: Bring up real data**

```bash
docker start blitzcast-postgres
cd backend  && .venv/Scripts/python -m uvicorn app.main:app --port 8000
rm -rf frontend/.next     # Next caches mock-mode 404s
cd frontend && npm run dev
```

- [ ] **Step 2: Verify in Chrome**

Navigate to a **2024 or 2025** week, which now has backfilled predictions and
real scores. Confirm:

- Scores render on cards; winner is emphasized.
- "Called it" / "Missed" badges appear and match the actual result.
- A final game with no prediction shows a score and no badge.
- The matchup page shows the score, the Final pill, the verdict band, the
  StatTicker result cell, and the reconstructed-prediction note.
- **Toggle the theme.** Verdict colors must be legible in light and dark, on
  cards and on the turf hero.
- Neutral-site and TBD-kickoff games still render correctly.
- Mobile viewport.

- [ ] **Step 3: Spot-check honesty**

Pick three finished games and confirm by hand that the badge matches who
actually won. A verdict that is silently inverted is the worst possible bug
here, and it looks fine until someone checks.

- [ ] **Step 4: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 3

Stop. This is the milestone worth the most scrutiny. Report:
- Screenshots of a finished week, both themes.
- The backfill accuracy numbers from Task 5 Step 6 against the backtest reports.
- Confirmation that reconstructed predictions are labeled.

---

# Milestone 5: Status filter

Spec §6.3, §9.

### Task 9: Backend status filter

**Files:**
- Modify: `backend/app/services/predictions.py:130-141`, `:144-157`, `:160-164`
- Modify: `backend/app/routers/games.py:19-25`, `backend/app/routers/schedule.py:19-25`
- Modify: `backend/app/mock_data.py:272-290`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `GameStatusFilter = Literal["all", "final", "upcoming"]`
- Produces: `_season_games(db, season, week=None, sport=SPORT_NFL, status="all")`

- [ ] **Step 1: Write the failing tests**

```python
def test_games_filter_final_returns_only_finished(client):
    body = client.get("/api/games?week=1&season=2026&status=final").json()
    assert all(g["home_score"] is not None for g in body)


def test_games_filter_upcoming_returns_only_unfinished(client):
    body = client.get("/api/games?week=1&season=2026&status=upcoming").json()
    assert all(g["home_score"] is None for g in body)


def test_games_unknown_status_falls_back_to_all(client):
    allg = client.get("/api/games?week=1&season=2026").json()
    junk = client.get("/api/games?week=1&season=2026&status=banana").json()
    assert len(junk) == len(allg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_api.py -k status -v`
Expected: FAIL

- [ ] **Step 3: Implement**

In `services/predictions.py`:

```python
GameStatusFilter = Literal["all", "final", "upcoming"]


def _apply_status(query, status: str):
    """Keyed on scores, not Game.status: that column is derived, unindexed,
    and NFL sets it final on the home score alone."""
    both = Game.home_score.is_not(None) & Game.away_score.is_not(None)
    if status == "final":
        return query.where(both)
    if status == "upcoming":
        return query.where(~both)
    return query
```

Add `status: str = "all"` to `_season_games`, `get_schedule`, and `get_games`,
and call `_apply_status(query, status)` inside `_season_games`.

In both routers, accept the param. Fall back silently rather than 422, matching
the existing `activeConf` tolerance on the frontend:

```python
    status: str = Query("all"),
```

and normalize with `status if status in ("all", "final", "upcoming") else "all"`.

- [ ] **Step 4: Mock parity**

`mock_data.get_games` and `get_schedule` must accept and honor `status`, or mock
mode silently ignores the filter.

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

### Task 10: Shared status filter component

**Files:**
- Create: `frontend/src/components/StatusFilter.tsx`
- Modify: `frontend/src/app/[sport]/page.tsx` (both `NflSlate` and `CfbSlate`)
- Modify: `frontend/src/lib/api.ts` (`getGames`, `getSchedule`)
- Test: `frontend/src/components/__tests__/StatusFilter.test.tsx`

**Interfaces:**
- Produces: `<StatusFilter sport={SportSlug} active={"all"|"final"|"upcoming"} week={number} query={string} />`

**Do not extend `FilterChips`.** It hardcodes `/cfb` (`FilterChips.tsx:24-25`)
and is conference-shaped. A separate component keeps both slates simple.

- [ ] **Step 1: Write the failing test**

```tsx
test("renders three status chips with the active one marked", () => {
  render(<StatusFilter sport="nfl" active="final" week={1} query="" />);
  expect(screen.getByText(/all/i)).toBeInTheDocument();
  expect(screen.getByText(/completed/i)).toBeInTheDocument();
  expect(screen.getByText(/upcoming/i)).toBeInTheDocument();
  expect(screen.getByText(/completed/i).closest("a")).toHaveAttribute(
    "aria-current",
    "true"
  );
});

test("links preserve the current week", () => {
  render(<StatusFilter sport="nfl" active="all" week={5} query="" />);
  expect(screen.getByText(/completed/i).closest("a")?.getAttribute("href")).toContain(
    "week=5"
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- StatusFilter`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Model it on `FilterChips.tsx` styling (`:27-30` class strings, `aria-current`
usage) but parameterize the base path by `sport`. Each chip is a `next/link`
that rebuilds the query preserving `week` and any existing filter params.

- [ ] **Step 4: Wire into both slates**

`NflSlate` currently has no filter UI and passes no `query` to `WeekSelector`
(`page.tsx:125`). Add both. **The status param must be included in
`filterQuery` (`page.tsx:172`) or the filter drops when the user changes week**.
This is the single easiest thing to get wrong here.

Read `status` from `searchParams` alongside `week`/`conf`/`top25`
(`page.tsx:16-23`), validate against the three known values, fall back to `"all"`.

- [ ] **Step 5: Empty state**

The `filtered` boolean (`page.tsx:197`) drives the empty-state copy (`:71-78`).
A status filter that matches nothing must say "No games match these filters",
not "No games scheduled for this week."

- [ ] **Step 6: Run tests**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 7: Verification gate**

Run the gate. Do not commit.

---

### Task 11: Hold the finished week until Tuesday morning

**Files:**
- Modify: `frontend/src/lib/format.ts:75-85`
- Test: `frontend/src/lib/__tests__/format.test.ts`

**Spec decision (§9): change the hold from 6 hours to 12.**

Every NFL week ends with Monday Night Football at 8:15 PM ET (verified against
2026 weeks 1-5). The week therefore stays current all day Monday on its own,
because MNF has not kicked off yet. What the hold controls is only how long
after MNF the finished slate stays up:

| Hold | Rolls over |
|---|---|
| 6h (current) | Tue 2:15 AM ET, before anyone would see it |
| **12h (target)** | **Tue 8:15 AM ET** |
| 36h | Wed 8:15 AM ET, too late; the audience is on Thursday by then |

**Do not touch `pickCfbDefaultWeek`** (`format.ts:94-100`). CFB is calendar-based
with a Monday 00:00 ET rollover, and CFB games end Saturday night, so Sunday
already serves as the review day.

The existing fixtures in this test file use Sunday-only weeks, which is not how
an NFL week ends. These cases add the Monday night game.

- [ ] **Step 1: Write the failing test**

```ts
// A realistic NFL week: a Sunday afternoon slate plus Monday Night Football.
// 2026-09-15T00:15Z is Mon Sep 14, 8:15 PM ET.
const withMnf = () =>
  schedule([
    ["2026-09-13T17:00:00Z", "2026-09-15T00:15:00Z"],
    ["2026-09-20T17:00:00Z", "2026-09-22T00:15:00Z"],
  ]);

test("Monday afternoon shows the current week, MNF has not kicked off", () => {
  // Mon Sep 14, 6:00 PM ET
  expect(pickDefaultWeek(withMnf(), new Date("2026-09-14T22:00:00Z"))).toBe(1);
});

test("late Monday night still shows the week just played", () => {
  // Mon Sep 14, 11:30 PM ET, right after MNF ends
  expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T03:30:00Z"))).toBe(1);
});

test("early Tuesday still shows the finished week", () => {
  // Tue Sep 15, 7:00 AM ET. This is the case the 6h hold gets wrong:
  // it rolled over at 2:15 AM and would return 2 here.
  expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T11:00:00Z"))).toBe(1);
});

test("by Tuesday mid-morning it has rolled to the new week", () => {
  // Tue Sep 15, 10:00 AM ET
  expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T14:00:00Z"))).toBe(2);
});
```

- [ ] **Step 2: Run tests to verify the right one fails**

Run: `cd frontend && npm test -- format`
Expected: **only** "early Tuesday still shows the finished week" FAILS, returning
2. The other three pass under the current 6h hold. If a different test fails,
re-read the fixture times before changing any code.

- [ ] **Step 3: Implement**

In `pickDefaultWeek` (`format.ts:76`), change the cutoff from 6 to 12 hours:

```ts
  // 12h past the last kickoff. An NFL week ends with Monday Night Football, so
  // this keeps the finished slate up overnight and rolls it Tuesday morning.
  const cutoff = now.getTime() - 12 * 60 * 60 * 1000;
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npm test -- format`
Expected: PASS, including all pre-existing `pickDefaultWeek` tests. The
pre-existing "sticks to the last week once the season is over" and
"a leftover TBD does not pin a finished week" cases must still pass; if either
breaks, the change is wrong.

- [ ] **Step 5: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 4

Stop. Report the filter working on both sports, surviving week navigation, and
the empty state.

---

# Milestone 6: Prediction record

Spec §6.4, §10.

### Task 12: Record endpoint

**Files:**
- Create: `backend/app/routers/record.py`
- Modify: `backend/app/main.py` (register the router)
- Modify: `backend/app/schemas.py` (add `RecordOut`)
- Modify: `backend/app/services/predictions.py` (add `get_record`)
- Test: `backend/tests/test_record.py`

**Interfaces:**
- Produces: `GET /api/record?sport=NFL|CFB&season=2026` returning `RecordOut`
- Produces: `RecordOut(sport: str | None, season: int, correct: int, total: int, market_correct: int, sufficient: bool)`

**Rules (spec §6.4):**
- Only games where `prediction_correct` is non-null.
- **Exclude backfilled predictions**: skip model versions starting with `backtest`.
- `market_correct` counts the **same** games, so both numbers share one sample.
  Games with no market data are excluded from **both**.
- `sufficient` is false below 10 graded games.
- Omitting `sport` returns combined totals. The frontend must not sum two calls.

- [ ] **Step 1: Write the failing tests**

```python
def test_record_excludes_backfilled_predictions(client, db):
    """Reconstructed backtest rows must never inflate the live record."""
    body = client.get("/api/record?sport=NFL&season=2026").json()
    assert body["total"] == 0  # 2026 has no finished games in the fixture


def test_record_reports_insufficient_sample(client):
    body = client.get("/api/record?sport=NFL&season=2026").json()
    assert body["sufficient"] is False


def test_record_market_baseline_shares_the_sample(client):
    body = client.get("/api/record?season=2026").json()
    assert body["market_correct"] <= body["total"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_record.py -v`
Expected: FAIL, 404 on the route.

- [ ] **Step 3: Implement `get_record`**

In `services/predictions.py`. Join `Game` to `Prediction`, filter to the season,
optionally the sport, require both scores, exclude
`Prediction.model_version.like("backtest%")`, and take the newest prediction per
game the same way `_prediction_probs` does (order ascending by `predicted_at`,
let later rows win).

For each graded game compute `prediction_verdict(...)`.

For the market baseline, **import the existing function rather than
reimplementing it**:

```python
from ml.features import market_home_prob
```

Signature (verified): `market_home_prob(home_ml, away_ml, spread_home) -> float | None`.
It de-vigs the moneyline pair when both are present and falls back to the spread
otherwise, returning `None` when neither exists. It is pure, with no DB or model
dependency.

`app/jobs/predict_week.py` already imports from `ml`, so this direction is
established; `app/services` importing `ml` is new but consistent. Do **not**
copy the de-vig arithmetic into the service layer. The spread-sign bug this repo
already shipped came from exactly that: one convention implemented in two
places, which then drifted.

Read each game's `home_moneyline`, `away_moneyline`, and `spread_line` from the
`Game` row, preferring a live `Odds` row when one exists, the same precedence
`ml/features.py` uses. A game where `market_home_prob` returns `None` is excluded
from **both** the model and market counts, so the two always share one sample.

Set `sufficient = total >= 10`.

- [ ] **Step 4: Add the route**

```python
router = APIRouter(prefix="/api", tags=["record"])


@router.get("/record", response_model=RecordOut, summary="Prediction record")
def get_record(
    sport: str | None = None, season: int = 2026, db: Session = Depends(get_db)
) -> RecordOut:
    return svc.get_record(db, season=season, sport=normalize_sport(sport) if sport else None)
```

Register it in `app/main.py` alongside the other routers, and add a mock-mode
branch consistent with the other endpoints.

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

### Task 13: Record display

**Files:**
- Create: `frontend/src/components/RecordBanner.tsx`
- Modify: `frontend/src/app/[sport]/page.tsx`
- Modify: `frontend/src/lib/api.ts` (add `getRecord`), `frontend/src/lib/types.ts` (add `Record`)
- Test: `frontend/src/components/__tests__/RecordBanner.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
test("shows the record next to the market baseline", () => {
  render(<RecordBanner record={{ sport: "NFL", season: 2026, correct: 11, total: 16, market_correct: 12, sufficient: true }} />);
  expect(screen.getByText(/11/)).toBeInTheDocument();
  expect(screen.getByText(/16/)).toBeInTheDocument();
  expect(screen.getByText(/market/i)).toBeInTheDocument();
});

test("shows an insufficient-sample state instead of a percentage", () => {
  render(<RecordBanner record={{ sport: "NFL", season: 2026, correct: 2, total: 3, market_correct: 2, sufficient: false }} />);
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  expect(screen.getByText(/not enough games/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- RecordBanner`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Render at the top of the slate. Always show the sample size. Below the
`sufficient` threshold, render "Not enough games yet" and no percentage.

**Never render the model's number without the market's beside it** (spec §10).
The model trails the market and the site says so; a lone figure reads as a claim
it cannot support.

- [ ] **Step 4: Wire into the slate**

Fetch in the page and pass down. Handle the fetch failing without breaking the
slate: the record is secondary, the games are the product.

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Verification gate**

Run the gate. Do not commit.

---

### Task 14: Week counter reads "correct" for finished weeks

**Files:**
- Modify: `frontend/src/app/[sport]/page.tsx:110,121-123` (NFL) and `:171,183-185` (CFB)

- [ ] **Step 1: Implement**

The counter currently always says "X/Y predicted". When every game in the
displayed week is final, count graded verdicts and say "X/Y correct" instead.
Mixed weeks keep the existing "predicted" wording.

- [ ] **Step 2: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 5

Stop. Report the record endpoint, the banner in both states, and confirm
backfilled rows are excluded.

---

# Milestone 7: Launch extras

Spec §11-14. All four are independent and can be parallelized across subagents.

### Task 15: OG share images

**Files:**
- Create: `frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx`
- Modify: `frontend/src/app/[sport]/matchup/[gameId]/page.tsx:30-38` (openGraph + twitter)

- [ ] **Step 1: Implement the image route**

Use Next's file-based `opengraph-image` convention with `ImageResponse`. Content:
both team abbreviations, the win probability, and Blitzcast branding. For a
finished game, the score and the verdict.

- [ ] **Step 2: Add the twitter card**

Add a `twitter` block to the exported metadata with `card: "summary_large_image"`.

- [ ] **Step 3: Verify locally**

Fetch `http://localhost:3000/nfl/matchup/<id>/opengraph-image` and confirm a PNG
renders with correct values.

- [ ] **Step 4: Note the deploy dependency**

`metadataBase` reads `NEXT_PUBLIC_SITE_URL` / `VERCEL_URL`
(`frontend/src/app/layout.tsx`). Record in the handoff that
`NEXT_PUBLIC_SITE_URL` must be set on Vercel or share previews resolve against
localhost. Font loading in the OG runtime is the usual failure mode; verify in
the deployed environment, not only locally.

- [ ] **Step 5: Verification gate**

Run the gate. Do not commit.

---

### Task 16: Model vs market disagreements

**Files:**
- Modify: `backend/app/services/predictions.py` (extend `GameSummary` population or add a small endpoint)
- Create: `frontend/src/components/Disagreements.tsx`
- Modify: `frontend/src/app/[sport]/page.tsx`

- [ ] **Step 1: Expose the market probability**

Add `market_home_prob: float | None` to `GameSummary`, computed by importing
`market_home_prob` from `ml.features` exactly as Task 12 does. Do not
reimplement the de-vig arithmetic.

Contract parity applies: `schemas.py`, the builder in `services/predictions.py`,
`app/mock_data.py`, `frontend/src/lib/types.ts`, and both frontend mock files.
See the five-place checklist in "Context for a fresh session".

- [ ] **Step 2: Build the component**

Show the largest absolute gaps between `home_win_prob` and `market_home_prob`
for the displayed week. Exclude games with no market data.

- [ ] **Step 3: Frame it correctly**

Present it as interesting, not as an edge. The site says "not betting advice"
and that must hold in tone as well as in the disclaimer. No language implying
the user should act on the gap.

- [ ] **Step 4: Verification gate**

Run the gate. Do not commit.

---

### Task 17: Methodology page

**Files:**
- Create: `frontend/src/app/how-it-works/page.tsx`
- Modify: `frontend/src/components/Footer.tsx` (link it)

- [ ] **Step 1: Write the page**

Plain language, broadcast voice, no em dashes. Cover: what the model uses, the
leakage rule, that Claude narrates but never predicts, and how often the model is
wrong **including the honest Vegas comparison**. Source material is in
`README.md` and `DECISIONS.md`.

- [ ] **Step 2: Do not overstate**

The model trails the market by roughly 3 points of accuracy. Say so. This page
exists to earn trust from a skeptical fan; overselling defeats its purpose.

- [ ] **Step 3: Verification gate**

Run the gate. Do not commit.

---

### Task 18: Sitemap and robots

**Files:**
- Create: `frontend/src/app/sitemap.ts`, `frontend/src/app/robots.ts`

- [ ] **Step 1: Implement**

Include both slates, the methodology page, and matchup URLs. **Do not fetch the
entire season on every sitemap request**; bound it to the current season and let
Next cache it.

- [ ] **Step 2: Verify**

Fetch `/sitemap.xml` and `/robots.txt` and confirm valid output.

- [ ] **Step 3: Verification gate**

Run the gate. Do not commit.

---

### Task 19: Temporal-disjointness guard

**Files:**
- Modify: `backend/ml/train.py`
- Test: `backend/tests/test_train_guard.py`

Spec §7.4. Nothing currently asserts training rows and prediction targets are
temporally disjoint. Someone could add 2026 to `TRAIN_SEASONS`, predict 2026
week 10, and the whole suite would pass green.

- [ ] **Step 1: Write the failing test**

```python
def test_training_rows_must_precede_the_calibration_set():
    from ml.train import assert_temporally_disjoint

    train = pd.DataFrame({"kickoff": pd.to_datetime(["2024-09-01", "2024-10-01"], utc=True)})
    calib = pd.DataFrame({"kickoff": pd.to_datetime(["2025-09-01"], utc=True)})
    assert_temporally_disjoint(train, calib)  # no raise

    overlapping = pd.DataFrame({"kickoff": pd.to_datetime(["2025-10-01"], utc=True)})
    with pytest.raises(ValueError, match="overlap"):
        assert_temporally_disjoint(overlapping, calib)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_train_guard.py -v`
Expected: FAIL, `ImportError`

- [ ] **Step 3: Implement**

```python
def assert_temporally_disjoint(train_df: pd.DataFrame, calib_df: pd.DataFrame) -> None:
    """Every training kickoff must precede every calibration kickoff.

    Without this, widening TRAIN_SEASONS to include the season being predicted
    would leak silently: no existing test covers train.py's split."""
    if train_df.empty or calib_df.empty:
        return
    latest_train = train_df["kickoff"].max()
    earliest_calib = calib_df["kickoff"].min()
    if latest_train >= earliest_calib:
        raise ValueError(
            f"training and calibration windows overlap: "
            f"latest train {latest_train} >= earliest calibration {earliest_calib}"
        )
```

Call it in `main()` immediately after the train/calib split.

- [ ] **Step 4: Run the full suite**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: PASS. If the existing split trips the guard, that is a real finding.
Investigate before relaxing the assertion.

- [ ] **Step 5: Verification gate**

Run the gate. Do not commit.

---

## 🚦 REVIEW CHECKPOINT 6

Stop. Report all four extras plus the guard.

---

# Milestone 8: Review, docs, handoff

Spec §20.

### Task 20: Full Chrome pass

**Files:** none. Verification only.

- [ ] **Step 1: Run the full checklist from spec §18**

Both sports, a completed week and an upcoming week, all four card states, both
themes on cards and turf, every status filter value plus week-change persistence
plus empty state, the record in both states, neutral-site and TBD games, the OG
image, and mobile.

- [ ] **Step 2: Record findings**

Screenshot anything that looks wrong. Fix before proceeding.

---

### Task 21: Code review and security review

- [ ] **Step 1: Code review**

Review backend and frontend diffs for correctness, contract drift, and anything
embarrassing in a public repo.

- [ ] **Step 2: Security review**

Run the `security-review` skill over the branch diff.

- [ ] **Step 3: Fix what surfaces**

Re-run the verification gate after fixes.

---

### Task 22: Documentation for v1.0.0

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `backend/README.md`, `frontend/README.md`, `DECISIONS.md`, `CLAUDE.md` if conventions changed
- Delete: `PROGRESS.md`

- [ ] **Step 1: Update the docs**

Record the new endpoints (`/api/record`, the `status` param), the backfill job,
the new frontend routes, and the known limitations from spec §16 (CFB postseason
never loads, no live game state).

- [ ] **Step 2: Add a CHANGELOG entry**

Under the existing `[1.0.0]` heading, not a new version. This ships as v1.0.0.

- [ ] **Step 3: Delete PROGRESS.md**

It was a scratch file for the release prep session.

- [ ] **Step 4: Final verification gate**

Run the gate one last time. **Do not commit. Do not push.** Hand back to the user
for review.

---

## Definition of done

- All tasks checked, all gates green.
- Chrome verified on real data, both sports, both themes.
- Backfill accuracy matches the backtest reports (the leak tripwire in Task 5).
- Reconstructed predictions labeled; record excludes them and shows the market
  baseline.
- Code review and security review complete, findings fixed.
- Docs updated for v1.0.0, `PROGRESS.md` deleted.
- **Nothing committed, nothing pushed.**
