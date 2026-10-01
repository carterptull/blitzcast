# P2 CFB In-Season Stats Implementation Plan (v1.0.13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load 2026 CFB team-game PPA (CFBD's EPA analogue) every day, so the CFB model's form features describe this season instead of one 2025 game (and then nothing from week 6 on).

**Architecture:** A new `refresh_stats_cfb` step, the CFB sibling of the NFL `refresh_stats`. It reuses `backfill_cfb.backfill_team_game_stats` (already idempotent: delete-then-insert scoped to the affected game ids) and is wired into the CFB orchestrator after the schedule sync. No model change; the existing CFB model was trained on these same columns.

**Tech Stack:** Python, SQLAlchemy, CFBD REST API, pytest.

**Spec:** [`docs/superpowers/specs/2026-09-30-booth-data-model-1.1-design.md`](../specs/2026-09-30-booth-data-model-1.1-design.md) (finding F3).

## Global Constraints

Everything in the spec's **Global constraints** applies. The ones that matter most here:
- A missing `CFBD_API_KEY` prints `WARNING:` and exits 0. A CFBD request failure exits 1, so `run_step` reports it without blocking later steps.
- Completion invariant: "played" means both scores.
- Git authorship is the maintainer's only, with no AI attribution.
- Production writes need the maintainer's go-ahead.

CFBD budget: one `/ppa/games` call per daily run (about 30 a month) on top of the existing schedule and poll calls.

Branch: `git checkout -b ct/feat/cfb-inseason-stats` off an up-to-date `main` (P1 merged).

---

### Task 1: `refresh_stats_cfb` step

**Files:**
- Create: `backend/data_pipeline/refresh_stats_cfb.py`
- Test: `backend/tests/test_refresh_stats_cfb.py`

**Interfaces:**
- Consumes: `data_pipeline.backfill_cfb.backfill_team_game_stats(db, season: int) -> int`
- Produces: `python -m data_pipeline.refresh_stats_cfb [--season 2026]` and `has_final_games(db, season: int) -> bool`

- [ ] **Step 1: Write the failing tests:**

```python
"""CFB in-season stats refresh: skips cleanly with no key or no finals."""
import sys
from unittest.mock import patch

import pytest

from app.models import Game
from data_pipeline import refresh_stats_cfb


def test_has_final_games_requires_both_scores(db):
    assert refresh_stats_cfb.has_final_games(db, 2026) is False
    game = db.get(Game, "cfb_401800001")
    game.home_score = 21
    db.flush()
    assert refresh_stats_cfb.has_final_games(db, 2026) is False  # half-scored
    game.away_score = 14
    db.flush()
    assert refresh_stats_cfb.has_final_games(db, 2026) is True


def test_missing_key_warns_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(refresh_stats_cfb.get_settings(), "cfbd_api_key", "")
    monkeypatch.setattr(sys, "argv", ["refresh_stats_cfb"])
    with pytest.raises(SystemExit) as exc:
        refresh_stats_cfb.main()
    assert exc.value.code == 0
    assert "WARNING" in capsys.readouterr().out


def test_cfbd_failure_exits_one(monkeypatch, db):
    import requests

    monkeypatch.setattr(refresh_stats_cfb.get_settings(), "cfbd_api_key", "k")
    monkeypatch.setattr(sys, "argv", ["refresh_stats_cfb"])
    monkeypatch.setattr(refresh_stats_cfb, "has_final_games", lambda *_: True)
    with patch.object(
        refresh_stats_cfb, "backfill_team_game_stats",
        side_effect=requests.RequestException("boom"),
    ), patch.object(refresh_stats_cfb, "session_scope") as scope:
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False  # don't swallow SystemExit
        with pytest.raises(SystemExit) as exc:
            refresh_stats_cfb.main()
    assert exc.value.code == 1
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_refresh_stats_cfb.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `backend/data_pipeline/refresh_stats_cfb.py`:**

```python
"""Load the current season's CFB team-game PPA into team_game_stats.

The rolling EPA form features read team_game_stats. Without this step the
in-progress CFB season has no rows, so "last 5 games" silently falls back to
last season and then to nothing.

Usage: python -m data_pipeline.refresh_stats_cfb [--season 2026]
"""

import argparse
import sys

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, Game
from data_pipeline.backfill_cfb import backfill_team_game_stats


def has_final_games(db: Session, season: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(Game)
        .where(
            Game.sport == SPORT_CFB,
            Game.season == season,
            Game.home_score.is_not(None),
            Game.away_score.is_not(None),
        )
    )
    return bool(count)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("WARNING: CFBD_API_KEY is not set; CFB stats not refreshed.")
        sys.exit(0)

    with session_scope() as db:
        if not has_final_games(db, args.season):
            print(f"cfb stats refresh: no final games for {args.season} yet, skipping.")
            return
        try:
            rows = backfill_team_game_stats(db, args.season)
        except requests.RequestException as exc:
            print(f"cfb stats refresh failed: {exc}")
            sys.exit(1)
    print(f"cfb stats refresh: upserted {rows} team_game_stats rows for {args.season}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests and lint.** Same pytest command plus `.venv\Scripts\python -m ruff check .`. Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/data_pipeline/refresh_stats_cfb.py backend/tests/test_refresh_stats_cfb.py
git commit -m "feat(cfb): daily refresh of current-season team-game PPA"
```

---

### Task 2: Wire it into the CFB orchestrator

**Files:**
- Modify: `backend/data_pipeline/refresh_week_cfb.py` (docstring and step list)
- Test: `backend/tests/test_refresh_week_cfb.py`

- [ ] **Step 1: Write the failing test** (append):

```python
def test_orchestrator_refreshes_stats_after_schedule_and_before_odds():
    import sys

    with patch.object(refresh_week_cfb, "run_step", return_value=True) as mock_run:
        with patch.object(sys, "argv", ["refresh_week_cfb", "--season", "2026", "--skip-predict"]):
            refresh_week_cfb.main()
    steps = [call.args[0] for call in mock_run.call_args_list]
    call = next(c for c in mock_run.call_args_list if c.args[0] == "cfb stats refresh")
    assert call.args[1] == ["data_pipeline.refresh_stats_cfb", "--season", "2026"]
    assert steps.index("cfb schedule sync") < steps.index("cfb stats refresh")
    assert steps.index("cfb stats refresh") < steps.index("cfb odds refresh")
```

- [ ] **Step 2: Run it and confirm it fails:** `.venv\Scripts\python -m pytest tests/test_refresh_week_cfb.py -v`.
- [ ] **Step 3: Implement.** After the schedule sync step add:

```python
    run_step("cfb stats refresh", ["data_pipeline.refresh_stats_cfb", "--season", season])
```

  Update the module docstring's first line to `schedule -> stats -> odds -> weather -> polls -> prediction batch`.
- [ ] **Step 4: Run the full suite and lint.** Expected: PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/data_pipeline/refresh_week_cfb.py backend/tests/test_refresh_week_cfb.py
git commit -m "feat(cfb): run the stats refresh in the daily CFB cron"
```

---

### Task 3: Docs, diagrams, and the v1.0.13 release

- [ ] **Step 1:** In `frontend/`, run `npm version 1.0.13 --no-git-tag-version`.
- [ ] **Step 2: CHANGELOG.** Add a `[1.0.13]` section. Under "Fixed": CFB predictions now use 2026 game stats; previously the daily CFB cron never loaded them, so CFB form features came from 2025.
- [ ] **Step 3: DECISIONS.md.** Add an entry for reusing `backfill_team_game_stats` daily. Why: it is already idempotent and scoped, and costs one CFBD call a day. Alternative: a week-scoped PPA call; it needs more code to save a single call.
- [ ] **Step 4: Diagrams.** Add the stats step to `daily-refresh-sequence.md` and, if it lists cfb-cron steps, to `c4-container.md`. Bump **every** diagram footer to `v1.0.13`.
- [ ] **Step 5: Final checks**, then push, open the PR, and wait for CI to pass. No AI attribution in the PR body.

```bash
git add -A
git commit -m "docs: changelog, decisions, and diagrams for 1.0.13"
git push -u origin ct/feat/cfb-inseason-stats
gh pr create --title "CFB in-season stats in the daily cron (1.0.13)" --body "<summary and test plan>"
```

---

### Task 4: Post-merge operations (each step needs the maintainer's go-ahead)

- [ ] **Step 1:** Run it once now instead of waiting for tomorrow's cron: `.venv\Scripts\python -m data_pipeline.refresh_stats_cfb --season 2026`.
- [ ] **Step 2: Verify (read-only):** `SELECT g.week, count(*) FROM team_game_stats s JOIN games g USING (game_id) WHERE g.sport='CFB' AND g.season=2026 GROUP BY 1 ORDER BY 1;` should show rows for every week with finals.
- [ ] **Step 3:** Re-run the current CFB week's predictions so they use the new stats: `.venv\Scripts\python -m app.jobs.predict_week --sport cfb`. This re-narrates with the current narrator, which is expected: P3 replaces it.
