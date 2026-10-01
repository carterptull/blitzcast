# P1 Data Correctness Implementation Plan (v1.0.12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (tasks share `features.py`, `predict_week.py`, and `explain.py`, so one sequential worker avoids conflicts). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the data bugs found in the 2026-09-30 review: missing weather that never self-heals, CFB neutral sites never flagged, moneyline sentinels reaching the UI, no-line games getting a phantom "Vegas" factor and a home-team bias, completion checks keyed on one score, and visible em dashes.

**Architecture:** Pipeline and feature-layer fixes with no retrain. The no-line fix imputes the two market features from Elo and adds a `has_market_line` flag. The flag is in the features frame's metadata (not a model input until P4), and it gates the explanation, the narration payload, and the backtest's market baseline.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, pandas, xgboost/shap, pytest, ruff; Next.js/TypeScript, Jest.

**Spec:** [`docs/superpowers/specs/2026-09-30-booth-data-model-1.1-design.md`](../specs/2026-09-30-booth-data-model-1.1-design.md) (findings F2, F4, F5, part of F1; decisions 7 and 8).

## Global Constraints

Everything in the spec's **Global constraints** section applies to every task. The ones this plan hits most:

- No em or en dashes in visitor-visible text; check literal characters and `&mdash;`/`&ndash;`.
- Completion invariant: both scores, never `Game.status`, never one score.
- Leakage rule: imputed market values use only pre-game Elo (already leakage-safe).
- Keys degrade gracefully: missing key prints `WARNING:` and exits 0. Every attempted call failing exits 1.
- Git authorship: maintainer's identity only, no AI trailers or attribution anywhere.
- Production writes need the maintainer's go-ahead at that step.

Branch: `git checkout -b ct/fix/data-correctness` off an up-to-date `main`.

---

### Task 1: Weather refresh fails loudly and back-fills missed games

**Files:**
- Modify: `backend/data_pipeline/refresh_weather.py`
- Modify: `backend/data_pipeline/refresh_week.py:33`, `backend/data_pipeline/refresh_week_cfb.py:35`
- Test: `backend/tests/test_refresh_weather.py`, `backend/tests/test_refresh_week_cfb.py`

**Interfaces:**
- Produces: `select_games(db, sport: str, now: datetime, days: int, backfill_days: int) -> list[Game]`, `exit_code(updated: int, failed: int) -> int`, CLI flag `--backfill-days N` (default 0).

- [ ] **Step 1: Write failing tests** in `backend/tests/test_refresh_weather.py`. Merge these imports into the file's existing import block at the top (ruff E402), then append the tests:

```python
import sys
from datetime import UTC, datetime, timedelta

import pytest

from app.models import SPORT_NFL, Game, Weather
from data_pipeline import refresh_weather
from data_pipeline.refresh_weather import exit_code, select_games


def _game(db, game_id, kickoff, home_id, away_id):
    db.add(Game(
        game_id=game_id, sport=SPORT_NFL, season=2026, week=3,
        game_date=kickoff.date(), kickoff_time=kickoff,
        home_team_id=home_id, away_team_id=away_id, status="scheduled",
    ))
    db.flush()


def test_backfill_picks_up_past_games_missing_weather(db):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    _game(db, "2026_03_BUF_KC", now - timedelta(days=4), 1, 2)
    _game(db, "2026_03_DAL_PHI", now - timedelta(days=4), 3, 4)
    db.add(Weather(game_id="2026_03_DAL_PHI", temp_f=70.0, captured_at=now))
    db.flush()

    ids = {g.game_id for g in select_games(db, SPORT_NFL, now, days=8, backfill_days=7)}
    assert "2026_03_BUF_KC" in ids
    assert "2026_03_DAL_PHI" not in ids  # already has weather


def test_no_backfill_keeps_the_forward_window_only(db):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    _game(db, "2026_03_BUF_KC", now - timedelta(days=4), 1, 2)
    ids = {g.game_id for g in select_games(db, SPORT_NFL, now, days=8, backfill_days=0)}
    assert "2026_03_BUF_KC" not in ids


def test_exit_code_fails_only_when_every_call_failed():
    assert exit_code(updated=0, failed=0) == 0
    assert exit_code(updated=5, failed=2) == 0
    assert exit_code(updated=0, failed=3) == 1


def test_missing_key_warns_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(refresh_weather.get_settings(), "visual_crossing_api_key", "")
    monkeypatch.setattr(sys, "argv", ["refresh_weather", "--sport", "cfb"])
    with pytest.raises(SystemExit) as exc:
        refresh_weather.main()
    assert exc.value.code == 0
    assert "WARNING" in capsys.readouterr().out
```

The team ids 1 to 4 are the NFL teams seeded first in `conftest._seed`. If the ids differ, look them up with `db.scalar(select(Team.team_id).where(Team.abbr == "KC"))`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_refresh_weather.py -v`
Expected: FAIL with `ImportError: cannot import name 'exit_code'`.

- [ ] **Step 3: Implement.** In `refresh_weather.py`:
  - Add `from sqlalchemy import exists, select`.
  - Update the module docstring's Usage line to `[--days 8] [--backfill-days 0] [--sport nfl|cfb]`.
  - Add these helpers above `main()`:

```python
def select_games(
    db, sport: str, now: datetime, days: int, backfill_days: int
) -> list[Game]:
    """Upcoming games in the look-ahead window, plus (with backfill_days) recent
    past games that never got a weather row: a missed run otherwise loses
    that game's weather for good."""
    window = (Game.kickoff_time >= now) & (Game.kickoff_time <= now + timedelta(days=days))
    if backfill_days:
        missed = (
            (Game.kickoff_time < now)
            & (Game.kickoff_time >= now - timedelta(days=backfill_days))
            & ~exists().where(Weather.game_id == Game.game_id)
        )
        window = window | missed
    return db.scalars(
        select(Game).options(joinedload(Game.stadium)).where(Game.sport == sport, window)
    ).all()


def exit_code(updated: int, failed: int) -> int:
    return 1 if failed and not updated else 0
```

  - In `main()`, add:

```python
    parser.add_argument(
        "--backfill-days", type=int, default=0, help="also fetch past games missing weather"
    )
```

  - Replace the missing-key branch with:

```python
    if not settings.visual_crossing_api_key:
        print("WARNING: VISUAL_CROSSING_API_KEY is not set; no weather fetched.")
        sys.exit(0)
```

  - Replace the inline `db.scalars(...)` query with `games = select_games(db, sport, now, args.days, args.backfill_days)`.
  - After the final summary `print`, add `sys.exit(exit_code(updated, failed))`.

- [ ] **Step 4: Wire the daily self-heal.** In `refresh_week.py` change the weather step to `run_step("weather refresh", ["data_pipeline.refresh_weather", "--backfill-days", "3"])`. In `refresh_week_cfb.py` change it to `["data_pipeline.refresh_weather", "--sport", "cfb", "--backfill-days", "3"]`. Update the expected list in `tests/test_refresh_week_cfb.py` to match.

- [ ] **Step 5: Run tests and lint**

Run: `.venv\Scripts\python -m pytest tests/test_refresh_weather.py tests/test_refresh_week_cfb.py -v; .venv\Scripts\python -m ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/data_pipeline/refresh_weather.py backend/data_pipeline/refresh_week.py backend/data_pipeline/refresh_week_cfb.py backend/tests/test_refresh_weather.py backend/tests/test_refresh_week_cfb.py
git commit -m "fix(weather): back-fill recently missed games and fail loudly when every call fails"
```

---

### Task 2: CFB loader records neutral sites and unmatched venues

**Files:**
- Modify: `backend/data_pipeline/cfb_games_loader.py:87`
- Test: `backend/tests/test_cfb_pipeline.py` (append)

**Interfaces:**
- Produces: CFB `Game.is_neutral_site` set from CFBD `neutralSite`. CFB `Game.venue_name` set to the raw CFBD venue when no Stadium row matched (same convention CLAUDE.md documents for NFL). Consumed by Task 1's weather fetch, P3's fact sheet, and P4's `is_neutral_site` feature.

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_cfb_pipeline.py`):

```python
import pandas as pd

from app.models import Game
from data_pipeline.cfb_games_loader import upsert_games


def test_neutral_site_and_unmatched_venue_are_recorded(db):
    games = pd.DataFrame([{
        "id": 401899999, "season": 2026, "week": 1,
        "startDate": "2026-08-29T16:00:00.000Z", "startTimeTBD": False,
        "homeTeam": "Georgia", "awayTeam": "Alabama",
        "venue": "Aviva Stadium", "neutralSite": True, "conferenceGame": True,
        "homePoints": None, "awayPoints": None, "completed": False,
    }])
    upsert_games(db, games)
    game = db.get(Game, "cfb_401899999")
    assert game.is_neutral_site is True
    assert game.stadium_id is None
    assert game.venue_name == "Aviva Stadium"


def test_matched_venue_keeps_venue_name_empty(db):
    games = pd.DataFrame([{
        "id": 401899998, "season": 2026, "week": 1,
        "startDate": "2026-08-29T16:00:00.000Z", "startTimeTBD": False,
        "homeTeam": "Georgia", "awayTeam": "Alabama",
        "venue": "Test Field", "neutralSite": False, "conferenceGame": True,
        "homePoints": None, "awayPoints": None, "completed": False,
    }])
    upsert_games(db, games)
    game = db.get(Game, "cfb_401899998")
    assert game.is_neutral_site is False
    assert game.stadium_id is not None
    assert game.venue_name is None
```

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python -m pytest tests/test_cfb_pipeline.py -k venue -v`
Expected: FAIL (`is_neutral_site` is False, `venue_name` is None).

- [ ] **Step 3: Implement.** Replace line 87 (`game.stadium_id = stadium_by_name.get(field(row, "venue"))`) with:

```python
        venue = field(row, "venue")
        game.stadium_id = stadium_by_name.get(venue)
        # Unmatched venues keep their raw name so weather can geocode them.
        game.venue_name = None if game.stadium_id else venue
        game.is_neutral_site = bool(field(row, "neutralSite", "neutral_site"))
```

- [ ] **Step 4: Run tests.** Same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/data_pipeline/cfb_games_loader.py backend/tests/test_cfb_pipeline.py
git commit -m "fix(cfb): record neutral sites and unmatched venue names from CFBD"
```

---

### Task 3: One shared moneyline sanity rule; filter sentinels at ingest and read

**Files:**
- Create: `backend/app/market.py`
- Modify: `backend/data_pipeline/cfbd.py:46-56`, `backend/ml/features.py:92-111`, `backend/data_pipeline/refresh_odds.py:34-50`, `backend/app/services/predictions.py:304-317`
- Test: `backend/tests/test_odds.py` (append), `backend/tests/test_api.py` (append)

**Interfaces:**
- Produces: `app.market.NO_QUOTE_SENTINEL = 100_000`, `real_moneyline(value) -> int | float | None`, `plausible_moneylines(home, away) -> bool`.

- [ ] **Step 1: Write failing tests** in `backend/tests/test_odds.py`. Add the `app.market` import to the top import block (`_consensus` is already imported there), then append the tests:

```python
from app.market import plausible_moneylines, real_moneyline


def test_real_moneyline_drops_sentinel():
    assert real_moneyline(-100000) is None
    assert real_moneyline(100000) is None
    assert real_moneyline(-8000) == -8000
    assert real_moneyline(None) is None


def test_plausible_moneylines():
    assert plausible_moneylines(-108, -112)        # pick'em vig
    assert plausible_moneylines(-10000, 2400)      # real blowout
    assert not plausible_moneylines(-100000, -100000)
    assert not plausible_moneylines(-5000, -5000)  # implied sum ~1.96
    assert not plausible_moneylines(None, 150)


def test_consensus_skips_a_sentinel_book_for_the_next_one():
    event = {
        "home_team": "Rutgers Scarlet Knights", "away_team": "Howard Bison",
        "bookmakers": [
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Rutgers Scarlet Knights", "price": -100000},
                {"name": "Howard Bison", "price": -100000},
            ]}]},
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Rutgers Scarlet Knights", "price": -20000},
                {"name": "Howard Bison", "price": 3500},
            ]}]},
        ],
    }
    assert _consensus(event, "RUTG", "HOW")["h2h"] == (-20000, 3500)
```

Append to `backend/tests/test_api.py` (uses the existing `client`/`db` fixtures; adjust the import list to what the file already has):

```python
def test_sentinel_moneylines_are_hidden_from_the_api(client, db):
    from datetime import UTC, datetime

    from app.models import Odds

    db.add(Odds(
        game_id="2026_01_BUF_KC", source="the-odds-api", spread_home=2.5,
        moneyline_home=-100000, moneyline_away=-100000, total=47.0,
        captured_at=datetime(2026, 9, 10, tzinfo=UTC),
    ))
    db.commit()
    odds = client.get("/api/predictions/2026_01_BUF_KC").json()["odds"]
    assert odds["moneyline_home"] is None
    assert odds["moneyline_away"] is None
    assert odds["spread_home"] == 2.5
```

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python -m pytest tests/test_odds.py tests/test_api.py -k "moneyline or consensus or sentinel" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.market'`.

- [ ] **Step 3: Create `backend/app/market.py`:**

```python
"""Sanity rules for quoted betting prices, shared by ingest, features, and the API."""

# Books and CFBD quote this as "no real price" on the extreme side of a blowout.
NO_QUOTE_SENTINEL = 100_000


def real_moneyline(value):
    return None if value is None or abs(value) >= NO_QUOTE_SENTINEL else value


def _implied(ml: float) -> float:
    return -ml / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def plausible_moneylines(home, away) -> bool:
    """Both sides real, and implied probabilities sum to a normal book (vig
    included). Rejects sentinel pairs and both-favorite glitches."""
    if real_moneyline(home) is None or real_moneyline(away) is None:
        return False
    return 0.95 <= _implied(home) + _implied(away) <= 1.25
```

- [ ] **Step 4: Point existing code at it.**
  - `cfbd.py`: delete the local `_NO_QUOTE_SENTINEL`/`_real_moneyline` block and its comment. Add `from app.market import real_moneyline` and use `real_moneyline(...)` in `load_lines`. `backend/tests/test_cfbd.py` imports the old name: change its import to `from app.market import real_moneyline` (keeping `from data_pipeline.cfbd import load_lines`) and rename the calls. Run `grep -rn "_real_moneyline\|_NO_QUOTE_SENTINEL" backend --include=*.py` and confirm nothing is left.
  - `features.py`: delete the local `_NO_QUOTE_SENTINEL` block. Add `from app.market import plausible_moneylines`. In `market_home_prob`, replace the four-part `if` condition with `if plausible_moneylines(home_ml, away_ml):`.
  - `refresh_odds.py` `_consensus`: add `from app.market import plausible_moneylines`, then replace the h2h branch with:

```python
            if key == "h2h" and home_name in outcomes and away_name in outcomes:
                pair = (outcomes[home_name]["price"], outcomes[away_name]["price"])
                if plausible_moneylines(*pair):
                    out["h2h"] = pair
```

    The `if key in out: continue` guard stays, so an implausible book no longer claims the h2h slot and the next book's pair is used.
  - `predictions.py`: add `from app.market import plausible_moneylines`, then add this helper next to `_market_prob`:

```python
def _shown_moneylines(home, away) -> tuple[int | None, int | None]:
    return (home, away) if plausible_moneylines(home, away) else (None, None)
```

    In both `OddsOut(...)` branches of `get_prediction_detail`, compute `ml_home, ml_away = _shown_moneylines(<home>, <away>)` from that branch's two fields and pass those instead of the raw fields.

- [ ] **Step 5: Run the whole backend suite** (a market-prob behavior change touches several tests):

Run: `.venv\Scripts\python -m pytest -q; .venv\Scripts\python -m ruff check .`
Expected: all PASS. If `test_market_home_prob_ignores_no_quote_sentinel` fails, read why before changing it: the new rule should still fall back to the spread for sentinel pairs.

- [ ] **Step 6: Commit**

```bash
git add backend/app/market.py backend/data_pipeline/cfbd.py backend/ml/features.py backend/data_pipeline/refresh_odds.py backend/app/services/predictions.py backend/tests/test_odds.py backend/tests/test_api.py
git commit -m "fix(odds): one moneyline sanity rule for ingest, features, and the API"
```

---

### Task 4: Completion invariant in features and the stats refresh

**Files:**
- Modify: `backend/ml/features.py:248` and `:470-474`, `backend/data_pipeline/refresh_stats.py` (the `played` count)
- Test: `backend/tests/test_features.py` (append)

- [ ] **Step 1: Write the failing test:**

```python
def test_half_scored_game_is_not_treated_as_played(db):
    """Completion invariant: a row with only one score has not finished."""
    week1 = db.scalars(select(Game).where(Game.game_id == "2025_01_BUF_KC")).one()
    week1.away_score = None
    db.flush()

    df = build_features(db)
    assert pd.isna(_feature_row(df, "2025_01_BUF_KC")["home_win"])
    # KC's week-2 form must not include the half-scored week-1 game.
    before = _feature_row(df, "2025_02_BUF_KC")["point_margin_diff"]
    assert pd.isna(before) or before == 0
```

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python -m pytest tests/test_features.py -k half_scored -v`
Expected: FAIL (`home_win` is 1.0 or 0.0).

- [ ] **Step 3: Implement.**
  - `features.py:248`: `played = games[games["home_score"].notna() & games["away_score"].notna()]`.
  - `features.py:470`: the `np.where` condition becomes `df["home_score"].isna() | df["away_score"].isna()`.
  - `refresh_stats.py` played count: add `Game.away_score.is_not(None)` next to the existing `Game.home_score.is_not(None)`.

- [ ] **Step 4: Run** `.venv\Scripts\python -m pytest tests/test_features.py tests/test_cold_start.py -v`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ml/features.py backend/data_pipeline/refresh_stats.py backend/tests/test_features.py
git commit -m "fix(features): a game counts as played only when both scores exist"
```

---

### Task 5: No-line games: Elo-imputed market features plus a `has_market_line` flag

**Files:**
- Modify: `backend/ml/features.py` (market block around `:438-446`, `meta` list at `:481-484`)
- Modify: `backend/ml/explain.py` (`top_factors`)
- Modify: `backend/app/jobs/predict_week.py` (`build_narration_payload`, the `top_factors` call)
- Modify: `backend/ml/backtest.py:136-137`
- Test: `backend/tests/test_features.py`, `backend/tests/test_explain.py`, `backend/tests/test_predict_week.py`

**Interfaces:**
- Produces: `build_features(...)` output gains meta column `has_market_line` (1.0 when the game had a real spread or a plausible moneyline pair, else 0.0); `market_spread_home`/`market_home_prob` are never NaN. `top_factors(..., market_available: bool = True)`. Consumed by P3 (fact sheet) and P4 (which moves `has_market_line` into `FEATURE_COLUMNS`).

- [ ] **Step 1: Write failing tests.**

`tests/test_features.py`:

```python
def test_no_line_game_gets_elo_imputed_market_and_a_flag(db):
    game = db.scalars(select(Game).where(Game.game_id == "2026_01_BUF_KC")).one()
    game.spread_line = None
    game.home_moneyline = None
    game.away_moneyline = None
    db.flush()

    row = _feature_row(build_features(db), "2026_01_BUF_KC")
    assert row["has_market_line"] == 0.0
    expected = (row["elo_diff"] + 55.0) / 25.0  # NFL HFA 55, 25 Elo per point
    assert abs(row["market_spread_home"] - expected) < 1e-9
    assert 0.0 < row["market_home_prob"] < 1.0


def test_lined_game_keeps_its_market_and_flag(db):
    row = _feature_row(build_features(db), "2026_01_PHI_DAL")
    assert row["has_market_line"] == 1.0
    assert row["market_spread_home"] == -3.5
```

`tests/test_explain.py`:

```python
def test_market_factors_are_skipped_when_no_line_exists():
    row = pd.DataFrame([{"market_spread_home": 4.0, "market_home_prob": 0.6, "elo_diff": 80.0}])
    explainer = _FakeExplainer([0.30, 0.20, 0.05])
    factors = top_factors(explainer, row, home_win_prob=0.7, n=3, market_available=False)
    assert [f["feature"] for f in factors] == ["elo_diff"]
```

`tests/test_predict_week.py`:

```python
def test_payload_hides_an_imputed_spread():
    teams = {
        "KC": _team(SPORT_NFL, "KC", "Kansas City Chiefs", "AFC", 1),
        "BUF": _team(SPORT_NFL, "BUF", "Buffalo Bills", "AFC", 2),
    }
    row = pd.Series({
        "home_abbr": "KC", "away_abbr": "BUF", "market_spread_home": 6.2,
        "has_market_line": 0.0, "is_divisional": 0.0,
    })
    payload = build_narration_payload(row, 0.7, [], teams, SPORT_NFL)
    assert payload["spread_home"] is None
```

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python -m pytest tests/test_features.py tests/test_explain.py tests/test_predict_week.py -k "line or imputed" -v`
Expected: FAIL (`KeyError: 'has_market_line'` / unexpected keyword `market_available`).

- [ ] **Step 3: Implement in `features.py`.** Add `import math` at the top. Below `market_home_prob`, add:

```python
ELO_PER_SPREAD_POINT = 25.0


def _spread_to_prob(spread_home: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-spread_home * ELO_PER_SPREAD_POINT / 400.0))


def _prob_to_spread(p: float) -> float:
    return math.log10(p / (1.0 - p)) * 400.0 / ELO_PER_SPREAD_POINT
```

Change `market_home_prob`'s spread fallback to `return _spread_to_prob(spread_home)` (same formula, now shared). Then replace the block that sets `df["market_spread_home"]` and `df["market_home_prob"]` (`:438-446`) with:

```python
    df["market_spread_home"] = df["spread_line"]
    df["market_home_prob"] = pd.to_numeric(
        df.apply(
            lambda r: market_home_prob(
                None if pd.isna(r["home_moneyline"]) else float(r["home_moneyline"]),
                None if pd.isna(r["away_moneyline"]) else float(r["away_moneyline"]),
                None if pd.isna(r["spread_line"]) else float(r["spread_line"]),
            ),
            axis=1,
        ),
        errors="coerce",
    )
    # No posted line: stand in an Elo-implied one so the model never routes a
    # missing market down the branch it learned from FCS mismatches. The flag
    # keeps the imputed line out of explanations, narration, and baselines.
    df["has_market_line"] = df["market_home_prob"].notna().astype(float)
    hfa = elo.config_for(sport).hfa
    elo_spread = (df["elo_home"] - df["elo_away"] + hfa) / ELO_PER_SPREAD_POINT
    ml_spread = df["market_home_prob"].map(_prob_to_spread, na_action="ignore")
    df["market_spread_home"] = df["market_spread_home"].fillna(ml_spread).fillna(elo_spread)
    df["market_home_prob"] = df["market_home_prob"].fillna(
        df["market_spread_home"].map(_spread_to_prob)
    )
```

`market_home_prob` is non-null whenever a spread or a plausible moneyline pair exists, so its `notna()` before imputation is exactly "a real line exists". Add `"has_market_line"` to the end of the `meta` list.

- [ ] **Step 4: Implement in `explain.py`.** Give `top_factors` the parameter `market_available: bool = True`. Replace the `order = ...[:n]` line with:

```python
    ranked = np.argsort(-np.abs(shap_values))
    if not market_available:
        ranked = [i for i in ranked if row.columns[i] not in _MARKET_GROUND_TRUTH]
    order = list(ranked)[:n]
```

- [ ] **Step 5: Implement in `predict_week.py`.**
  - In `build_narration_payload`, replace the `spread = row.get("market_spread_home")` line with:

```python
    has_line = bool(row.get("has_market_line", 1.0))
    spread = row.get("market_spread_home") if has_line else None
```

  - In `main()`, change the factors call to `top_factors(explainer, x, prob, sport=sport, market_available=bool(row["has_market_line"]))`.

- [ ] **Step 6: Implement in `backtest.py`.** Lines 136-137 become:

```python
        market = eval_df["market_home_prob"].to_numpy(dtype=float)
        has_market = eval_df["has_market_line"].to_numpy(dtype=float) == 1.0
```

  This keeps imputed Elo values out of the "Vegas" baseline.

- [ ] **Step 7: Run the full suite and lint**

Run: `.venv\Scripts\python -m pytest -q; .venv\Scripts\python -m ruff check .`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/ml/features.py backend/ml/explain.py backend/app/jobs/predict_week.py backend/ml/backtest.py backend/tests/test_features.py backend/tests/test_explain.py backend/tests/test_predict_week.py
git commit -m "fix(ml): impute no-line market features from Elo and keep them out of explanations"
```

---

### Task 6: Replace visible em-dash placeholders

**Files:**
- Modify: `frontend/src/components/StatTicker.tsx:36,53,54`, `frontend/src/components/MatchupHero.tsx:64`, `frontend/src/lib/format.ts:63`, `frontend/src/lib/og.ts:49,54`
- Test: `frontend/src/lib/__tests__/format.test.ts:109-115`, `frontend/src/lib/__tests__/og.test.ts:50-51`

- [ ] **Step 1: Update the tests first.** In `format.test.ts`, rename the two tests to "...renders N/A" and expect `"N/A"`. In `og.test.ts`, expect `"TBD"` for the pending `value`s.
- [ ] **Step 2: Run** `npm test -- format og` from `frontend/`. Expected: FAIL.
- [ ] **Step 3: Implement.** `format.ts:63` returns `"N/A"`. `StatTicker.tsx` lines 36, 53, 54 use `"N/A"`. `MatchupHero.tsx:64` renders `TBD`. `og.ts:49,54` return `"TBD"`. Update the `og.ts:12` doc comment to say `"TBD"`.
- [ ] **Step 4: Sweep for anything missed.** From `frontend/src`, run `grep -rn "—\|–\|&mdash;\|&ndash;" --include=*.tsx --include=*.ts . | grep -v __tests__`. Every remaining hit must be inside a comment. Fix any string a visitor can see.
- [ ] **Step 5: Run** `npm run lint; npm test; npm run build`. Expected: all pass.
- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "fix(ui): replace visible em-dash placeholders with N/A and TBD"
```

---

### Task 7: Docs, diagrams, and the v1.0.12 release

**Files:** `frontend/package.json`, `frontend/package-lock.json`, `CHANGELOG.md`, `DECISIONS.md`, every file in `diagrams/`, `diagrams/daily-refresh-sequence.md`, `diagrams/ml-pipeline.md`, `diagrams/game-lifecycle-state.md`

- [ ] **Step 1:** In `frontend/`, run `npm version 1.0.12 --no-git-tag-version`.
- [ ] **Step 2: CHANGELOG.** Add a `## [1.0.12] — 2026-MM-DD` section (fill in the merge date) under `[Unreleased]`, with "Fixed" bullets for:
  - weather back-fill plus the loud failure exit code
  - CFB neutral sites and venue names
  - moneyline sentinels hidden at ingest and on read
  - no-line games no longer claim a Vegas lean or skew to the home team
  - the completion invariant in features and the stats refresh
  - N/A and TBD placeholders

  (The CHANGELOG heading itself uses the existing format; it is not visitor-visible.)
- [ ] **Step 3: DECISIONS.md.** Add three entries in the file's existing format (heading, what, **Why:**, **Alternative:**):
  1. Elo-imputed market features with a `has_market_line` flag. Why: no-line rows trained on FCS mismatches, all 8 no-line 2026 games got 75 to 86% home. Alternative: retrain with a missing-line indicator only (P4 adds the flag as a feature too).
  2. One `plausible_moneylines` rule shared by ingest, features, and the API. Alternative: clamp in the UI only.
  3. Weather `--backfill-days`. Why: forward-only selection made one missed day permanent, and the free tier serves historical days. Alternative: a separate historical job.
- [ ] **Step 4: Diagrams.**
  - `daily-refresh-sequence.md`: the weather step now includes "plus past 3 days missing weather", and a run where every call fails exits 1.
  - `ml-pipeline.md`: market features are imputed from Elo when no line exists, with the `has_market_line` flag.
  - `game-lifecycle-state.md`: confirm it already says both scores. If it names call sites, add `features.py`.
  - Bump **every** diagram footer to `_Last updated: <date> · reflects v1.0.12_`.
  - Check that the Mermaid syntax follows `diagrams/README.md`'s rules.
- [ ] **Step 5: Final checks.** Backend `.venv\Scripts\python -m pytest -q` and `ruff check .`. Frontend `npm run lint`, `npm test`, `npm run build`.
- [ ] **Step 6: Commit, push, PR.**

```bash
git add -A
git commit -m "docs: changelog, decisions, and diagrams for 1.0.12"
git push -u origin ct/fix/data-correctness
gh pr create --title "Data correctness: weather back-fill, CFB neutral sites, odds sanity, no-line games (1.0.12)" --body "<summary of tasks 1-6 and the test plan; no AI attribution lines>"
```

Wait for CI to pass. The maintainer merges.

---

### Task 8: Post-merge operations (each step needs the maintainer's go-ahead)

- [ ] **Step 1 (maintainer, Railway):** on the **cfb-cron** service, confirm `VISUAL_CROSSING_API_KEY` is set (copy it from nfl-cron if missing). Confirm the latest cfb-cron log shows `weather refresh (cfb): updated N` with N > 0, not a `WARNING:` line.
- [ ] **Step 2: One-time weather back-fill.** Only past games without a row are fetched, so this is safe to re-run. Visual Crossing's free tier is 1000 records/day; if the output shows failures (429), run the same command the next day.

```bash
.venv\Scripts\python -m data_pipeline.refresh_weather --sport cfb --days 0 --backfill-days 40
.venv\Scripts\python -m data_pipeline.refresh_weather --sport nfl --days 0 --backfill-days 40
```

- [ ] **Step 3: Refresh the CFB schedule** so 2026 games pick up `is_neutral_site`/`venue_name`: `.venv\Scripts\python -m data_pipeline.refresh_schedule_cfb --season 2026`.
- [ ] **Step 4: Verify (read-only).**
  - CFB 2026 weather rows per week are non-zero for weeks 1, 3 and 4.
  - `SELECT count(*) FROM games WHERE sport='CFB' AND season=2026 AND is_neutral_site` is greater than 0.
  - In the browser, Howard @ Rutgers (`/cfb/matchup/cfb_401858468`) shows no `-100000` moneyline, and a no-line game (`/cfb/matchup/cfb_401864504`) has no "Vegas point spread" factor after the next daily prediction run.
