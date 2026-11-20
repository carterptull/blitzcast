# Postseason Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show, predict, narrate and grade every NFL playoff game and every FBS bowl/CFP game as the feeds publish them, behind a Regular season / Postseason toggle.

**Architecture:** One migration adds `season_type`, `round`, `event_name` and CFP seeds to `games`; one module (`app/postseason.py`) owns every round rule and label. Loaders fill the new columns (CFB postseason stored at slate week 17), a new `/api/slates` endpoint drives a data-driven chip strip and default slate, and the frontend adds the phase toggle, round chips, event badges and neutral-site "vs". Release 2 teaches the booth the occasion, seeds, stakes and split records.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (`Mapped`), Alembic, pandas, pytest, ruff; Next.js 16 App Router, TypeScript, Tailwind v4, Jest.

**Spec:** `docs/superpowers/specs/2026-11-19-postseason-design.md` (approved 2026-11-19, revision 2). Read it first; this plan argues from it. Where the spec and this plan differ, **the spec wins**: fix the plan, not the spec, unless the maintainer agrees.

## Spec Traceability (how the spec is embedded in the code)

- Every test that proves a requirement cites its ID: in the docstring for Python (`"""PS-C4: ..."""`), in the `it`/`describe` title for Jest (`it("PS-F3: unknown round falls back to default", ...)`).
- `backend/tests/test_spec_traceability.py` (Task 1) enforces it with an explicit `PENDING` set. Each task's final step removes its IDs from `PENDING`.
- Task-to-ID map:

| Task | Requirement IDs |
|---|---|
| 1 | PS-D4, PS-D5, PS-C5 (cleaner and naming rules) |
| 2 | PS-D1, PS-D2, PS-D3 |
| 3 | PS-N1, PS-N2, PS-N3, PS-N4 |
| 4 | PS-C1 to PS-C4, PS-C6 to PS-C11 |
| 5 | PS-O1 to PS-O4 (+ MC-1) |
| 6 | PS-M1, PS-M2, PS-M3 |
| 7 | PS-J1 to PS-J4 |
| 8 | PS-A2 to PS-A6, PS-A1 (backend half) |
| 9 | PS-A1 (frontend half; same ID, both tests cite it) |
| 10 | PS-F1, PS-F2, PS-F3, PS-F12, PS-V1 |
| 11 | PS-F4, PS-F5, PS-F6, PS-F10, PS-F13, PS-V2 |
| 12 | PS-F7, PS-F8, PS-F9, PS-F11, PS-V3 |
| 13 | MC-2, MC-4, MC-5; assert `PENDING` is a subset of PS-B* |
| 14 | PS-B1 to PS-B5 |
| 15 | PS-B6, PS-B7 |
| 16 | MC-3; assert `PENDING` is empty |

## Global Constraints

- Release 1 = v1.3.0, merged and deployed by **2026-12-03**. Release 2 = v1.3.1 by **2026-12-12**. First bowl 2026-12-15; Selection Day 2026-12-06; NFL Wild Card 2027-01-16.
- No model retrain; `MODEL_VERSION` stays `1.0.0`, `MODEL_VERSION_CFB` stays `cfb-1.0.0`; committed `.joblib`/`latest.json` untouched.
- Leakage rule: features for game G use only data from strictly before G's kickoff. Never load CFBD postseason rankings.
- Completion invariant: "is this game over" is always `home_score is not None and away_score is not None`, never `Game.status`.
- Visitor-visible copy: no em/en dashes, and no `&mdash;`/`&ndash;`, including feed-derived `event_name`.
- Branding: "Paymon" / "Paymon Software" only.
- New API fields touch all five places in one change: `backend/app/schemas.py`, `backend/app/services/predictions.py`, `backend/app/mock_data.py`, `frontend/src/lib/types.ts` (nullability exact), `frontend/src/lib/mock.ts` + `mockCfb.ts`; asserted in `frontend/src/lib/__tests__/api.test.ts`.
- Game id rule `^[A-Za-z0-9_-]{1,32}$` unchanged on both sides.
- `app/market.py` stays the only moneyline plausibility rule. Odds fetched by batch only (500 req/month).
- Schema changes only through Alembic. Python deps stay pinned. Comments minimal.
- Postseason identity comes from `season_type`/`round`, never from week arithmetic (new CLAUDE.md invariant, written in Task 13).
- Every test that proves a requirement cites its `PS-` ID; every task ends by removing its IDs from `PENDING` in `test_spec_traceability.py` (see Spec Traceability). Product code carries no requirement IDs (CLAUDE.md: comments minimal); `app/postseason.py`'s docstring is the one pointer to the spec.
- Git: branch `ct/feat/postseason` from main (Release 2: `ct/feat/postseason-booth`). Commits and PR bodies carry **no** attribution lines of any kind (no Co-Authored-By, no session links). PR body via `--body-file`; `gh pr checks --watch`; merge `gh pr merge --merge --delete-branch` outside 09:00 to 10:00 UTC.
- Production: every production write (migration, manual sync, re-predict) and every paid API call needs the maintainer's go-ahead at that step. Phase 0 (Task 0) is pre-approved for the LOCAL database only.
- Commands run from `backend/` with `.venv\Scripts\python -m ...`, and from `frontend/` with `npx jest ...` / `npm run lint` / `npm run build`.

## Review Focus

1. **CFBD row with `playoff` null, or a bowl with no `bowlName` and odd `notes`.** Expect: still loaded at week 17 with `round='bowl'` and a generic or cleaned name, never dropped. Test in Task 4 (`test_postseason_row_without_playoff_object_is_a_bowl`).
2. **Selection Day reshuffle: kickoff, venue or bowl changes after a row first exists.** Expect: next sync overwrites them. Test in Task 4 (`test_postseason_upsert_overwrites_kickoff_venue_and_event`).
3. **Odds event in swapped orientation for a NON-neutral game.** Expect: no match (only neutral games may swap). Test in Task 5 (`test_swapped_orientation_ignored_for_home_games`).
4. **Hand-typed URLs: `/cfb?round=bogus`, `/cfb?week=17`, `/nfl?round=bowls`, a round chip with zero games.** Expect: unknown values fall back to the default slate; an empty published slate shows the empty-state copy. Test in Task 10 (`resolveSlate` cases) and Task 11.
5. **Feed bowl name with an en dash, "presented by" tail, or 3+ digits.** Expect: cleaned or replaced by the generic name; no dash ever reaches the API. Test in Task 1 (`test_clean_event_name_*`) and Task 12 (copy scan).

---

## File Structure

Backend
- Create `backend/app/postseason.py`: round enum, slugs, labels, Super Bowl numeral, `CFB_POSTSEASON_WEEK`, event-name cleaner, championship detector. Pure functions, no DB.
- Create `backend/alembic/versions/d5a1c7e3f9b2_add_game_postseason_fields.py`.
- Modify `backend/app/models.py` (Game columns), `data_pipeline/games_loader.py`, `data_pipeline/cfbd.py`, `data_pipeline/cfb_games_loader.py`, `data_pipeline/refresh_schedule_cfb.py`, `data_pipeline/refresh_stats_cfb.py`, `data_pipeline/refresh_odds.py`, `data_pipeline/refresh_injuries.py`, `app/services/predictions.py`, `app/jobs/predict_week.py`, `app/jobs/coverage.py`, `ml/features.py`, `app/schemas.py`, `app/routers/games.py`, create `app/routers/slates.py` (+ register in `app/main.py`), `app/mock_data.py`.
- Release 2: `app/services/fact_sheet.py`, `app/services/narrate.py`, `app/services/fallback_narration.py`, `ml/explain.py`.

Frontend
- Modify `src/lib/types.ts`, `src/lib/api.ts`, `src/lib/format.ts`, `src/lib/og.ts`, `src/lib/mock.ts`, `src/lib/mockCfb.ts`, `src/app/[sport]/page.tsx`, `src/app/[sport]/matchup/[gameId]/page.tsx`, `src/app/[sport]/matchup/[gameId]/opengraph-image.tsx`, `src/components/GameCard.tsx`, `src/components/MatchupHero.tsx`, `src/components/Disagreements.tsx`, `src/components/StatusFilter.tsx`, `src/components/FilterChips.tsx`, `src/app/how-it-works/page.tsx`.
- Rename `src/components/WeekSelector.tsx` -> `src/components/SlateSelector.tsx` (and its test).
- Create `src/components/PhaseToggle.tsx` (+ test).

---

## Phase A: groundwork (review pause after Task 2)

### Task 0: Phase 0 check on 2025 data (LOCAL only)

**Status 2026-11-19:**
- Steps 2-3 are DONE read-only. Findings are in `.superpowers/sdd/2026-11-19-postseason/phase0-findings.md`, and the raw JSON is in `phase0-data/` there. Use the raw JSON as test fixtures in Tasks 1, 4 and 8.
- Still to do at build time: Step 1, Step 4, and a dry run of the real loaders against the fixtures in the local DB.

**Files:**
- Create: `.superpowers/sdd/2026-11-19-postseason/phase0.py` (git-excluded, throwaway)
- Create: `.superpowers/sdd/2026-11-19-postseason/phase0-findings.md`

- [ ] **Step 1:** Confirm `DATABASE_URL` in `backend/.env` points at the local Docker Postgres (not Railway). Stop if it doesn't.
- [ ] **Step 2:** Script calls `cfbd._get("/games", {"year": 2025, "seasonType": "postseason", "classification": "fbs"})` and `cfbd._get("/games", {"year": 2025, "seasonType": "regular", "week": 14})` (also week 15 and 16), and `cfbd._get("/calendar", {"year": 2026})`. Log every call (count them; expect 5 to 6). Save raw JSON beside the script.
- [ ] **Step 3:** Record in findings: postseason `week` value(s); `notes` for bowls, CFP games and title games; `playoff` object keys and `round` values; `neutralSite` for CFP first-round games; whether any row has a non-FBS or placeholder team; the exact signal that marks a conference championship (notes text, `conferenceGame`, week); 2026 calendar week for title games and Army-Navy; any en/em dash in `notes`.
- [ ] **Step 4:** Query local odds for neutral-site regular-season CFB games and report how many have no odds row today (input for Task 5's before/after count). Read-only.
- [ ] **Step 5:** If a finding contradicts the spec, adjust the affected task in this plan, note it in the findings file, and carry it to DECISIONS in Task 13.

### Task 1: Spec in the repo, traceability test, `app/postseason.py`

**Files:**
- Commit first: `docs/superpowers/specs/2026-11-19-postseason-design.md`, `docs/superpowers/plans/2026-11-19-postseason.md` (first commit on `ct/feat/postseason`, message `docs(postseason): add design spec and implementation plan`)
- Create: `backend/tests/fixtures/cfbd_post_2025.json`, `cfbd_reg_2025_w15.json`, `nflverse_playoffs_2025.csv`. Trim them from `.superpowers/sdd/2026-11-19-postseason/phase0-data/` and the nflverse `games.csv` exactly as Appendix A of the spec describes, and drop fields we don't read (line scores, Elo, highlights) to keep them small.
- Create: `backend/tests/test_spec_traceability.py`
- Create: `backend/app/postseason.py`
- Test: `backend/tests/test_postseason.py`

**Traceability test (write before anything else in this task):**
- `spec_ids()` reads the spec and returns every `PS-[A-Z]+\d+` match.
- `cited_ids()` scans the text of `backend/tests/**/*.py` (excluding this file) and `frontend/src/**/__tests__/**` + `frontend/src/**/*.test.*`.
- `PENDING: set[str]` starts as every spec ID.
- Tests:
  - `test_every_implemented_requirement_has_a_test`: `spec_ids() - PENDING <= cited_ids()`
  - `test_pending_ids_have_no_test_yet`: `not (PENDING & cited_ids())` (forces removing an ID from `PENDING` once its test lands)
  - `test_pending_ids_exist_in_spec`: `PENDING <= spec_ids()`
- Every later task's last step before committing: remove its IDs from `PENDING` and run this file.
- `app/postseason.py` module docstring: `"""Postseason rounds, labels and event names. Spec: docs/superpowers/specs/2026-11-19-postseason-design.md"""`

**Interfaces:**
- Produces:
  - `SEASON_REGULAR = "regular"`, `SEASON_POSTSEASON = "postseason"`, `CFB_POSTSEASON_WEEK = 17`, `NFL_GAME_TYPES = ("REG", "WC", "DIV", "CON", "SB")`
  - `Round = Literal["conf_championship", "wild_card", "divisional", "conference", "super_bowl", "bowl", "cfp_first_round", "cfp_quarterfinal", "cfp_semifinal", "cfp_championship", "cfp_other"]`; `ROUNDS: tuple[Round, ...]`
  - `ROUND_SLUGS: dict[Round, str]`: wild-card, divisional, conference, super-bowl, bowls, cfp-first-round, cfp-quarterfinals, cfp-semifinals, cfp-title, cfp-other (`conf_championship` has no slug; it is a regular week)
  - `round_for_slug(slug: str) -> Round | None`
  - `ROUND_LABELS: dict[Round, tuple[str, str, str]]` = (full label, chip group line, chip short label): wild_card ("Wild Card", "Round", "WC"), divisional ("Divisional", "Round", "DIV"), conference ("Conference Championships", "Round", "CONF"), super_bowl ("Super Bowl", "Round", "SB"), bowl ("Bowl Season", "Non-CFP", "Bowls"), cfp_first_round ("CFP First Round", "CFP", "R1"), cfp_quarterfinal ("CFP Quarterfinals", "CFP", "QF"), cfp_semifinal ("CFP Semifinals", "CFP", "SF"), cfp_championship ("National Championship", "CFP", "Title"), cfp_other ("College Football Playoff", "CFP", "CFP"), conf_championship ("Conference Championships", "Champ", None)
  - `nfl_round(game_type: str) -> tuple[str, Round | None]` (raises `ValueError` on unknown)
  - `roman(n: int) -> str`; `super_bowl_name(season: int) -> str`
  - `nfl_event_name(round_: Round, home_conference: str | None, season: int) -> str`
  - `cfb_playoff_round(raw: str | None) -> Round`
  - `clean_event_name(raw: str | None) -> str | None`; `generic_event_name(round_: Round) -> str`
  - `cfp_event_name(raw_round: str | None, bowl_name: str | None) -> str`: "<Bowl>, <generic round>" when the cleaned bowl name ends in "Bowl", else the generic round name ("CFP National Championship" for championship)
  - `is_conf_championship(notes: str | None, home_conference: str | None, away_conference: str | None) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
def test_nfl_round_maps_game_types():
    assert nfl_round("REG") == ("regular", None)
    assert nfl_round("WC") == ("postseason", "wild_card")
    assert nfl_round("SB") == ("postseason", "super_bowl")
    with pytest.raises(ValueError):
        nfl_round("PRO")

def test_super_bowl_name_2026_is_lxi():
    assert super_bowl_name(2026) == "Super Bowl LXI"
    assert super_bowl_name(2025) == "Super Bowl LX"

def test_nfl_event_names():
    assert nfl_event_name("wild_card", "AFC", 2026) == "AFC Wild Card"
    assert nfl_event_name("conference", "NFC", 2026) == "NFC Championship"
    assert nfl_event_name("super_bowl", "NFC", 2026) == "Super Bowl LXI"

def test_cfb_playoff_round_maps_known_and_unknown():
    assert cfb_playoff_round("quarterfinal") == "cfp_quarterfinal"
    assert cfb_playoff_round("championship") == "cfp_championship"
    assert cfb_playoff_round("second_round") == "cfp_other"
    assert cfb_playoff_round(None) == "cfp_other"

def test_clean_event_name_strips_dashes_and_sponsor_tails():
    assert clean_event_name("Rose Bowl Game – CFP Quarterfinal") == "Rose Bowl Game, CFP Quarterfinal"
    assert clean_event_name("Pop-Tarts Bowl presented by Kellogg") == "Pop-Tarts Bowl"
    assert clean_event_name("Duke's Mayo Bowl") == "Duke's Mayo Bowl"
    assert clean_event_name("68 Ventures Bowl") == "68 Ventures Bowl"

def test_clean_event_name_real_2025_notes():
    assert clean_event_name("Sheraton Hawaiʻi Bowl") == "Sheraton Hawai'i Bowl"
    assert clean_event_name("IS4S Salute to Veterans Bowl") == "IS4S Salute to Veterans Bowl"
    assert clean_event_name("Radiance Technologies Independence Bowl") == "Radiance Technologies Independence Bowl"

def test_cfp_event_name_uses_bowl_only_when_it_is_a_bowl():
    assert cfp_event_name("quarterfinal", "Cotton Bowl") == "Cotton Bowl, CFP Quarterfinal"
    assert cfp_event_name("first_round", "College Football Playoff First Round Game") == "CFP First Round"
    assert cfp_event_name("championship", "College Football Playoff National Championship Presented by AT&T") == "CFP National Championship"

def test_clean_event_name_rejects_junk():
    assert clean_event_name("Bowl 2026-27 Game 12345") is None
    assert clean_event_name("x" * 60) is None
    assert clean_event_name(None) is None
    assert clean_event_name("Visit http://x.y") is None

def test_generic_event_names():
    assert generic_event_name("bowl") == "Bowl game"
    assert generic_event_name("cfp_quarterfinal") == "CFP Quarterfinal"
    assert generic_event_name("cfp_other") == "College Football Playoff"

def test_is_conf_championship():
    assert is_conf_championship("SEC Championship", "SEC", "SEC")
    assert not is_conf_championship("SEC Championship", "SEC", "Big Ten")
    assert not is_conf_championship(None, "SEC", "SEC")

def test_slugs_round_trip():
    for r, slug in ROUND_SLUGS.items():
        assert round_for_slug(slug) == r
    assert round_for_slug("bogus") is None

def test_no_label_contains_a_dash():
    for full, group, short in ROUND_LABELS.values():
        for text in (full, group, short or ""):
            assert "–" not in text and "—" not in text
```

- [ ] **Step 2:** Run `python -m pytest tests/test_postseason.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `app/postseason.py`. `clean_event_name`: apply `fact_sheet._clean(raw, 64)` first (import it; it is the one feed-text cleaner); map U+02BB, U+2018 and U+2019 to `'`; replace `–`/`—` with ", "; drop a case-insensitive `\s+(presented|powered|hosted)\s+by\b.*$` tail; collapse spaces; reject (return None) unless it matches `^[A-Za-z0-9'&.,\- ]{3,48}$` with at most 2 digits total. `is_conf_championship`: notes contains "championship" (case-insensitive) and both conferences are equal and non-null. Never use CFBD `conferenceGame`; it is False for every 2025 title game (Phase 0).
- [ ] **Step 4:** Run tests. Expected: PASS. `python -m ruff check app/postseason.py tests/test_postseason.py` clean. Each test docstring cites its PS ID (e.g. `"""PS-C5: ..."""`).
- [ ] **Step 5:** Remove PS-D4, PS-D5, PS-C5 from `PENDING`; run `python -m pytest tests/test_spec_traceability.py`. Expected: PASS.
- [ ] **Step 6:** Commit `feat(postseason): add round rules, event-name cleaner and spec traceability`.

### Task 2: Migration and Game columns

**Files:**
- Create: `backend/alembic/versions/d5a1c7e3f9b2_add_game_postseason_fields.py` (down_revision `c3f1a9d27e48`)
- Modify: `backend/app/models.py:67-99`
- Test: `backend/tests/test_postseason.py` (append)

**Interfaces:**
- Produces on `Game`: `season_type: Mapped[str]` (String(12), default/server_default `"regular"`, CHECK in regular/postseason), `round: Mapped[str | None]` (String(24), CHECK in `ROUNDS`), `event_name: Mapped[str | None]` (String(64)), `home_seed: Mapped[int | None]`, `away_seed: Mapped[int | None]` (SmallInteger).

- [ ] **Step 1: Failing test** `test_game_defaults_to_regular_season` (create a Game via the existing conftest DB fixture; assert `season_type == "regular"` and `round is None`), and `test_round_check_rejects_unknown_value` (insert `round="bogus"`, expect `IntegrityError`).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Add the columns and the migration. Upgrade also backfills NFL history:
  `UPDATE games SET season_type='postseason', round=CASE ... END WHERE sport='NFL' AND ((season>=2021 AND week>=19) OR (season<2021 AND week>=18))` mapping weeks 19/20/21/22 (pre-2021: 18/19/20/21) to wild_card/divisional/conference/super_bowl, and `event_name` for Super Bowls via `super_bowl_name` computed in Python per season. Downgrade drops the columns and constraints.
- [ ] **Step 4:** Run tests; then locally `python -m alembic upgrade head` and `python -m alembic downgrade -1` and `upgrade head` again. Expected: clean both ways.
- [ ] **Step 5:** Commit `feat(db): add season type, round, event name and seeds to games`.

**Review pause: show the maintainer Task 0 findings plus Tasks 1-2 diff.**

---

## Phase B: data and jobs (review pause after Task 7)

### Task 3: NFL loader

**Files:**
- Modify: `backend/data_pipeline/games_loader.py:54-118`
- Test: `backend/tests/test_games_loader.py`

**Interfaces:**
- Consumes: `nfl_round`, `nfl_event_name` (Task 1); Game columns (Task 2).
- Produces: `upsert_games(db, schedules) -> int` unchanged signature; skipped rows are logged as `skipped NFL row <game_id>: <reason>`.

- [ ] **Step 1: Failing tests:**
  - `test_wild_card_row_gets_round_and_event` (game_type WC, home in AFC -> season_type postseason, round wild_card, event_name "AFC Wild Card")
  - `test_super_bowl_is_neutral_and_named` (SB, location Neutral, stadium "SoFi Stadium" present in `stadiums` -> is_neutral_site True, venue_name kept, `stadium_id` linked by name, event_name "Super Bowl LXI")
  - `test_neutral_game_with_unknown_stadium_keeps_null_stadium`
  - `test_unresolvable_team_row_is_skipped_not_fatal` (one row with team "TBD" among two good rows -> returns 2, no exception)
  - `test_missing_gameday_row_is_skipped`
  - `test_unknown_game_type_row_is_skipped`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Filter `game_type` to `NFL_GAME_TYPES`; per-row `try/except (KeyError, ValueError, TypeError)` that logs and continues; set the new columns; for neutral rows look up `Stadium` by exact `name` (build a `{name: stadium_id}` map once).
- [ ] **Step 4:** Run `python -m pytest tests/test_games_loader.py -v`. Expected: PASS (existing tests too).
- [ ] **Step 5:** Commit `feat(nfl): load playoff rounds, link neutral stadiums, isolate bad rows`.

### Task 4: CFB postseason ingestion

**Files:**
- Modify: `backend/data_pipeline/cfbd.py:45-46`, `backend/data_pipeline/cfb_games_loader.py:51-200`, `backend/data_pipeline/refresh_schedule_cfb.py:16-30`, `backend/data_pipeline/refresh_stats_cfb.py:38-150`
- Test: `backend/tests/test_cfb_pipeline.py`, `backend/tests/test_cfbd.py`, `backend/tests/test_refresh_stats_cfb.py`

**Interfaces:**
- Consumes: Task 1 helpers, `CFB_POSTSEASON_WEEK`.
- Produces: `cfbd.load_games(year: int, season_type: str = "regular", classification: str | None = None) -> pd.DataFrame`; `cfb_games_loader.upsert_games(db, games) -> tuple[int, int]` handles both season types, reading `seasonType` per row.

- [ ] **Step 1: Failing tests (fixtures shaped like Phase 0 raw JSON):**
  - `test_postseason_bowl_stored_at_slate_week_17` (seasonType postseason, week 1 -> week 17, season_type postseason, round bowl, event_name from `playoff.bowlName` or `notes`)
  - `test_cfp_game_gets_round_and_seeds` (playoff.round quarterfinal, homeSeed 4, awaySeed 5 -> round cfp_quarterfinal, seeds stored, event_name "Fiesta Bowl, CFP Quarterfinal" or as Phase 0 shows)
  - `test_unknown_playoff_round_is_cfp_other`
  - `test_postseason_row_without_playoff_object_is_a_bowl` (Review Focus 1)
  - `test_postseason_upsert_overwrites_kickoff_venue_and_event` (Review Focus 2: upsert twice with changed startDate, venue, notes, neutralSite)
  - `test_conference_championship_tagged_in_week_14` (regular week 14, notes "SEC Championship", both SEC -> round conf_championship, event_name "SEC Championship", season_type regular)
  - `test_championship_without_signal_still_loads` (no notes -> round None, game present)
  - `test_fcs_postseason_rows_skipped` (Celebration Bowl FCS vs FCS -> skipped; also D-II/D-III rows)
  - `test_real_2025_postseason_fixture_loads_46_fbs_games` (load `phase0-data/post_2025.json`, copied into `backend/tests/fixtures/cfbd_post_2025.json` trimmed to the 46 FBS rows plus 3 non-FBS rows: 46 stored at week 17, 11 with a CFP round, seeds on all 11, first-round games not neutral, Hawai'i Bowl not neutral, event names contain no dash)
  - `test_real_2025_championships_tagged` (fixture from `reg_2025_w15.json`: 9 games get `conf_championship`; a regular week-14 game does not)
  - `test_regular_week_at_or_above_postseason_slate_week_is_rejected` (a regular-season row with week 17 logs an error and is skipped, so it can never mix into the postseason slate)
  - `test_refresh_schedule_fetches_regular_and_postseason` (monkeypatch `load_games`; assert called with `("regular")` and `("postseason", classification="fbs")`)
  - `test_load_rankings_only_ever_regular` (grep-style test: every call site of `load_rankings` in `data_pipeline/` passes no season type or `"regular"`; leakage guard)
  - `test_stats_refresh_includes_postseason_games`
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Postseason rows require both `homeClassification` and `awayClassification` == "fbs" when present (else existing `should_skip_game`). Every upsert assigns kickoff, venue, neutral flag, round, event_name and seeds (no "only if empty"). Event name: `clean_event_name(playoff.bowlName)` then `clean_event_name(notes)` then `generic_event_name(round)`; for CFP rounds with a bowl, `f"{bowl}, {generic_event_name(round)}"` unless the cleaned notes already contain the round words. Stats refresh: fetch `load_team_game_ppa(year, "postseason")` too and upsert the same way.
- [ ] **Step 4:** Run the three test files. Expected: PASS.
- [ ] **Step 5:** Indoor venues: using Phase 0's raw venues, check the loader's exact-name `Stadium` match resolves the domed postseason sites (Mercedes-Benz Stadium, Caesars Superdome, State Farm Stadium, AT&T Stadium, Ford Field, Lucas Oil Stadium, Allegiant Stadium, NRG Stadium). For any miss, add the CFBD spelling to `seeds/stadiums.json` (no schema change) and a test `test_postseason_dome_venue_links_stadium`, so weather reads indoors.
- [ ] **Step 6:** Commit `feat(cfb): ingest bowls and CFP games as postseason slate`.

### Task 5: Odds orientation and TBD-time injuries

**Files:**
- Modify: `backend/data_pipeline/refresh_odds.py:56-150`, `backend/data_pipeline/refresh_injuries.py:26-38`
- Test: `backend/tests/test_odds.py`, create `backend/tests/test_refresh_injuries.py`

**Interfaces:**
- Produces: `refresh_odds.match_event(games_by_pair: dict[tuple[int, int], Game], home_id: int, away_id: int) -> tuple[Game | None, bool]` (game, swapped); `_consensus` gains `swapped: bool = False` and when True returns prices re-oriented to the stored home team (spread sign flipped via `book_spread_to_home`, moneylines swapped).

- [ ] **Step 1: Failing tests:**
  - `test_neutral_game_matches_in_swapped_orientation` (stored home DET, book lists DET away -> matched, spread and moneylines flipped)
  - `test_swapped_orientation_ignored_for_home_games` (Review Focus 3)
  - `test_exact_orientation_preferred_over_swap`
  - `test_tbd_kickoff_game_receives_injuries` (`_next_game_by_team` returns a game with NULL kickoff whose `game_date >= today`)
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Swap only when `game.is_neutral_site`. Moneyline plausibility still goes through `app/market.py` unchanged.
- [ ] **Step 4:** Run tests. Then count, against the LOCAL database, how many neutral regular-season games gain an odds match (dry run, no write); record the number for the CHANGELOG.
- [ ] **Step 5:** Commit `fix(odds): match neutral-site games listed in either orientation`.

### Task 6: Polls and features for postseason

**Files:**
- Modify: `backend/app/services/predictions.py:45-68`, `backend/app/jobs/predict_week.py:392-418`, `backend/ml/features.py:438,481-493`
- Test: `backend/tests/test_cfb_polls.py`, `backend/tests/test_cfb_features.py`

**Interfaces:**
- Produces: `predictions.latest_regular_poll_ranks(db, sport: str, season: int) -> dict[int, int]` (AP preferred, highest regular-season poll week present); `poll_ranks_entering` returns it when `week == CFB_POSTSEASON_WEEK`. `ranks_for_week` returns `(latest, latest)` for week 17 (no previous-rank movement in the postseason).

- [ ] **Step 1: Failing tests:**
  - `test_postseason_ranks_use_latest_regular_poll` (polls at weeks 14 and 15 -> week 17 gets week 15's)
  - `test_postseason_ranks_never_read_a_postseason_poll` (a PollRank row at week 1 inserted as if postseason must not be used for week 17)
  - `test_postseason_feature_poll_strength_from_latest_regular_poll`
  - `test_postseason_week_number_feature_clamped_to_16` (week 17 CFB row -> `week_number == 16.0`; NFL week 22 unchanged)
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement the shared rule; in `build_features` join postseason rows to the max regular poll week of that season, and clamp CFB `week_number` with `min(week, 16)` only for `season_type == "postseason"` (add `season_type` to the games frame in `_load_frames`).
- [ ] **Step 4:** Run tests plus `tests/test_features.py tests/test_cfb_features.py` (leakage tests must still pass).
- [ ] **Step 5:** Commit `feat(ml): postseason games use the latest regular-season poll`.

### Task 7: Prediction job and coverage

**Files:**
- Modify: `backend/app/jobs/predict_week.py:333-389,248-313,514+`, `backend/app/jobs/coverage.py:33-80`
- Test: `backend/tests/test_predict_week.py`, `backend/tests/test_coverage.py`

**Interfaces:**
- Produces: `select_target_ids(...)` additionally returns every unplayed published postseason game of the season (no week limit); new `in_narration_window(row, now: datetime, lookahead_days: int = LOOKAHEAD_DAYS) -> bool`; `narrate_safely` receives `allow_claude: bool` and when False goes straight to the template (counts as `fallback`). `check_coverage` expects a prediction and a booth for every unplayed published postseason game.

- [ ] **Step 1: Failing tests:**
  - `test_postseason_games_beyond_window_are_predicted` (bowl 20 days out -> in targets)
  - `test_claude_not_called_outside_window` (stub client; game 20 days out -> zero Claude calls, narration source `fallback`)
  - `test_claude_called_inside_window`
  - `test_coverage_counts_postseason_games_beyond_window`
  - `test_default_week_unchanged_for_regular_season` (existing behaviour pinned)
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Near-even games keep their existing template path. The summary line format is unchanged.
- [ ] **Step 4:** Run `python -m pytest tests/test_predict_week.py tests/test_coverage.py -v` then the full suite `python -m pytest`. Expected: all pass (record the count).
- [ ] **Step 5:** Commit `feat(jobs): predict every postseason game, narrate with Claude inside the window`.

**Review pause: show the maintainer Phase B diff summary and the odds before/after count.**

---

## Phase C: API and frontend (review pause after Task 12)

### Task 8: API contract and `/api/slates`

**Files:**
- Modify: `backend/app/schemas.py:21-125`, `backend/app/services/predictions.py:141-233,290-385`, `backend/app/routers/games.py:14-35`, `backend/app/main.py`, `backend/app/mock_data.py`
- Create: `backend/app/routers/slates.py`
- Test: `backend/tests/test_api.py`, `backend/tests/test_api_hardening.py`

**Interfaces:**
- Produces:
  - `GameSummary` + `season_type: Literal["regular", "postseason"] = "regular"`, `round: str | None = None`, `event_name: str | None = None`, `is_neutral_site: bool = False`, `home_seed: int | None = None`, `away_seed: int | None = None`
  - `PredictionOut` + the same five (not `is_neutral_site`; it is in `venue`)
  - `SlateOut(key: str, phase: Literal["regular", "postseason"], week: int, round: str | None, label: str | None, group_label: str, short_label: str, game_count: int, first_kickoff: datetime | None, next_kickoff: datetime | None, has_unscheduled: bool, last_kickoff: datetime | None)`. Keys: regular `"w{N}"`, postseason the round slug. NFL weeks 19-22 are postseason slates keyed by slug. Regular slates: `group_label` "Wk", `short_label` str(N); a week containing any `conf_championship` game gets `label` "Conference Championships", `group_label` "Champ". `next_kickoff` = earliest kickoff later than now minus 12 h; `has_unscheduled` = any game with NULL kickoff and no scores.
  - `GET /api/slates?season=2026&sport=NFL|CFB` -> `list[SlateOut]`, ordered regular weeks ascending then postseason by `ROUNDS` order; cached 60 s like `/api/schedule`.
  - `GET /api/games` + `round: str | None = Query(None, pattern=r"^[a-z-]{1,24}$")` (slug); unknown slug -> 422.
  - `get_games(db, season, week, sport, status, round_slug: str | None = None)`.
- [ ] **Step 1: Failing tests:**
  - `test_game_summary_carries_postseason_fields`
  - `test_slates_nfl_regular_then_rounds` (weeks 1..18 then wild-card, divisional, conference, super-bowl with short labels WC/DIV/CONF/SB)
  - `test_slates_cfb_champ_week_label` (week 14 with one championship + one stray game -> label "Conference Championships", group "Champ")
  - `test_slates_cfb_postseason_split_by_round` (week 17 bowls + CFP -> separate slates; bowls before cfp-first-round)
  - `test_games_round_filter` (`week=17&round=bowls` returns only bowls)
  - `test_games_bad_round_slug_422`
  - `test_mock_mode_slates_and_postseason_fixtures` (mock returns at least one postseason slate per sport)
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement service `get_slates(db, season, sport, now: datetime | None = None) -> list[SlateOut]`, router, `_game_summary` fields, `get_prediction_detail` fields, and mock fixtures in `mock_data.py`: NFL weeks 19-22 (Super Bowl neutral at SoFi), CFB week 14 with 2 championships, week 17 with 2 bowls, 2 first-round and 1 quarterfinal game with seeds.
- [ ] **Step 4:** Run `python -m pytest tests/test_api.py tests/test_api_hardening.py -v`, then full suite and `python -m ruff check .`.
- [ ] **Step 5:** Commit `feat(api): postseason fields, round filter and slates endpoint`.

### Task 9: Frontend contract and fixtures

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts:60-79`, `frontend/src/lib/mock.ts`, `frontend/src/lib/mockCfb.ts`
- Test: `frontend/src/lib/__tests__/api.test.ts`

**Interfaces:**
- Produces in `types.ts`: `SeasonType = "regular" | "postseason"`; `Round` (same 11 strings); `GameSummary` + `season_type: SeasonType; round: Round | null; event_name: string | null; is_neutral_site: boolean; home_seed: number | null; away_seed: number | null`; `MatchupDetail` + `season_type`, `round`, `event_name`, `home_seed`, `away_seed`; `Slate { key: string; phase: SeasonType; week: number; round: Round | null; label: string | null; group_label: string; short_label: string; game_count: number; first_kickoff: string | null; next_kickoff: string | null; has_unscheduled: boolean; last_kickoff: string | null }`.
- In `api.ts`: `getSlates(season = 2026, sport: Sport = "NFL"): Promise<Slate[]>`; `getGames(week, season, sport, status, round?: string)`.
- Fixtures mirror Task 8's mock set; every new game id passes `isGameId`; one fixture `event_name` exercises the cleaned-dash case (already cleaned, so it contains no dash).

- [ ] **Step 1: Failing tests** in `api.test.ts`: `mock games carry postseason fields with exact nullability`, `mock slates include postseason rounds for both sports`, `getGames passes round slug`, `every mock postseason id passes isGameId`.
- [ ] **Step 2:** `npx jest src/lib/__tests__/api.test.ts`; expect FAIL.
- [ ] **Step 3:** Implement types, client, fixtures (dates in Dec 2026 / Jan to Feb 2027).
- [ ] **Step 4:** Run jest file, then `npx tsc --noEmit`. Expected: PASS, no type errors.
- [ ] **Step 5:** Commit `feat(frontend): postseason contract types and fixtures`.

### Task 10: Default slate and URL resolution

**Files:**
- Modify: `frontend/src/lib/format.ts:72-102`
- Test: `frontend/src/lib/__tests__/format.test.ts`

**Interfaces:**
- Produces: `pickDefaultSlate(slates: Slate[], now?: Date): Slate | undefined`; `resolveSlate(slates: Slate[], params: { week?: string; round?: string }, now?: Date): Slate | undefined`; `slateHref(basePath: string, slate: Slate, query?: string): string` (`?week=N` or `?round=slug`); `eyebrowText(season: number, slate: Slate): string`. Removes `CFB_WEEKS`, `pickCfbDefaultWeek`, `pickDefaultWeek` (and their tests).
- Algorithm (spec section 5): candidates = postseason slates if any exist, else all; live = `next_kickoff !== null || has_unscheduled`; if a live slate with `round` starting `cfp_` has `next_kickoff - now <= 7 days`, pick the soonest such; else the live slate with the smallest `next_kickoff` (unscheduled-only slates sort after dated ones); else the last candidate.

- [ ] **Step 1: Failing tests** (fixtures built from the spec's 2026-27 calendar):
  - `pickDefaultSlate` CFB table: 2026-12-01 -> `w14`; 12-08 -> `bowls`; 12-14 -> `cfp-first-round`; 12-21 -> `bowls`; 12-26 -> `cfp-quarterfinals`; 2027-01-04 -> `cfp-semifinals`; 01-20 -> `cfp-title`
  - NFL table: 2027-01-05 -> `w18`; 01-12 -> `wild-card`; 01-20 -> `divisional`; 01-26 -> `conference`; 02-03 -> `super-bowl`
  - `pickDefaultSlate` with no postseason slates behaves like today's rule (week 12 mid-November)
  - `resolveSlate` cases (Review Focus 4): `{week:"14"}` -> w14 even when postseason exists; `{round:"bowls"}` -> bowls; `{round:"bogus"}` -> default; `{week:"17"}` -> default; NFL `{round:"bowls"}` -> default
  - `eyebrowText`: "2026 Season · Week 12", "2026 Season · Conference Championships", "2026 Postseason · Wild Card", "2026 Postseason · CFP Quarterfinals"
- [ ] **Step 2:** `npx jest src/lib/__tests__/format.test.ts`; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(frontend): data-driven default slate across both phases`.

### Task 11: Slate page, toggle and chips

**Files:**
- Modify: `frontend/src/app/[sport]/page.tsx`, `frontend/src/components/StatusFilter.tsx`, `frontend/src/components/FilterChips.tsx`
- Rename: `WeekSelector.tsx` -> `SlateSelector.tsx` (and test)
- Create: `frontend/src/components/PhaseToggle.tsx`
- Test: `src/components/__tests__/SlateSelector.test.tsx`, `src/components/__tests__/PhaseToggle.test.tsx`, `src/app/[sport]/__tests__/page.test.tsx`, `StatusFilter.test.tsx`, `FilterChips.test.tsx`

**Interfaces:**
- Produces: `SlateSelector({ slates, selectedKey, basePath, query })` (chip: `group_label` over `short_label`, `aria-current` on active, prefetch off, scroll into view as today); `PhaseToggle({ phase, regularHref, postseasonHref })` (renders nothing when `postseasonHref` is null; inactive Postseason side shows the gold dot; uses StatusFilter `on`/`off` tokens); `StatusFilter`/`FilterChips` take a `slateQuery: string` (`week=N` or `round=slug`) instead of `week: number`.
- Page: both sports call `getSlates` + `resolveSlate`; NFL games still come from `getSchedule` by `slate.week`; CFB from `getGames(slate.week, 2026, "CFB", status, slate.phase === "postseason" ? slate.key : undefined)`; strip shows only the active phase's slates; label "Select a week" / "Select a round"; conference and Top 25 chips shown for regular weeks and `bowls`; Banner takes `eyebrow: string`.
- Empty published slate copy: "Matchups are set as each round is decided." (no dash).

- [ ] **Step 1: Failing tests:** SlateSelector renders "Champ / 14", "Round / WC", "CFP / QF" and hrefs `?week=14`, `?round=wild-card`; PhaseToggle hidden when no postseason, links correct, dot only on inactive Postseason; page test: CFB with postseason slates opens Postseason by default but `?week=14` opens Week 14 (spec 6b); StatusFilter keeps `round=bowls` in links.
- [ ] **Step 2:** Run those jest files; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `npx jest` (all), `npm run lint`, `npx tsc --noEmit`.
- [ ] **Step 5:** Commit `feat(frontend): regular season and postseason toggle with round chips`.

### Task 12: Cards, matchup page, share image

**Files:**
- Modify: `GameCard.tsx`, `MatchupHero.tsx`, `Disagreements.tsx`, `src/app/[sport]/matchup/[gameId]/page.tsx`, `.../opengraph-image.tsx`, `src/lib/og.ts`, `src/app/how-it-works/page.tsx`, `backend/ml/explain.py:22`, `backend/app/mock_data.py:96`
- Test: `GameCard.test.tsx`, `MatchupHero.test.tsx`, `Disagreements.test.tsx`, `og.test.ts`, `format.test.ts`, `backend/tests/test_explain.py`

**Interfaces:**
- Produces in `format.ts`: `matchupSeparator(neutral: boolean): "vs" | "@"`; `matchupTitle(m: MatchupDetail): string` ("BUF vs DET, Super Bowl LXI"; "KC @ BUF, Week 5"); `backLink(m: MatchupDetail, sport): { href: string; label: string }` ("Back to Wild Card" -> `/nfl?round=wild-card`; "Week 5 slate" -> `/nfl?week=5`). `OgContent` gains `occasion: string` (event_name or `Week N`) and `separator`.

- [ ] **Step 1: Failing tests:** GameCard shows event badge and "(5)" seed instead of "#7" rank when a seed exists; no badge for regular games; MatchupHero eyebrow is `event_name`, center mark "vs" for neutral, badge reads "Division game"; Disagreements uses "vs" for neutral; og footer "Super Bowl LXI · 2026"; `matchupTitle`/`backLink` cases; `test_division_factor_label` in backend; a copy scan test asserting none of the new strings (labels, badges, empty state, How It Works paragraph) contains `–`, `—`, `&mdash;` or `&ndash;`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Event badge = Prime time pill classes plus `bg-gold/10 border-gold`. How It Works: one short paragraph on postseason (neutral sites, bowl opt-outs not modeled, market shown alongside).
- [ ] **Step 4:** Full frontend suite, lint, `npm run build` with `NEXT_PUBLIC_USE_MOCK=1`; backend `python -m pytest tests/test_explain.py`.
- [ ] **Step 5:** Commit `feat(frontend): event badges, seeds and neutral-site wording`.

**Review pause: mock-mode production build in Chrome (light and dark, phone width): NFL and CFB, both phases, every chip, a matchup page, an OG image. Screenshots to the maintainer.**

---

## Phase D: ship Release 1

### Task 13: Docs, reviews, release v1.3.0

**Files:** `CHANGELOG.md`, `DECISIONS.md`, `CLAUDE.md`, `README.md`, `backend/README.md`, `diagrams/*.md` (schema ER, pipeline, prediction read path, narration boundary) and every footer stamp, `frontend/package.json` (1.3.0).

- [ ] **Step 0:** `test_spec_traceability.py`: `PENDING` now holds only `PS-B*` IDs; add `test_release_1_complete` asserting `all(i.startswith("PS-B") for i in PENDING)`.
- [ ] **Step 1:** CLAUDE.md: add the three invariants in spec §11 verbatim, plus a link to the spec under Conventions; note `/api/slates` in Architecture.
- [ ] **Step 2:** DECISIONS: slate-week-17 storage, toggle + default rule, Claude window for far-off games, poll rule (leakage), no retrain, Phase 0 findings, odds swap and its regular-season count. CHANGELOG lists the regular-season-affecting fixes. READMEs drop the "no CFB postseason" limitation.
- [ ] **Step 3:** Diagrams updated per `diagrams/README.md` re-check table; footers `reflects v1.3.0`.
- [ ] **Step 4:** Grep visitor-visible files for `–|—|&mdash;|&ndash;`; expect none new. Run backend `python -m pytest` + `ruff`, frontend `npx jest`, `npm run lint`, `npm run build`.
- [ ] **Step 5:** One fresh whole-branch code review and security review; fix findings.
- [ ] **Step 6:** Push, PR (body via `--body-file`, no attribution), `gh pr checks --watch`, merge outside 09:00 to 10:00 UTC, tag and GitHub release v1.3.0 from the CHANGELOG.
- [ ] **Step 7 (each needs the maintainer's go-ahead, asked at the time):** run the migration on production; read-only production query confirming 2026 Week 14 holds the 10 title games with `round='conf_championship'` (spec 6b); optional manual `refresh_week_cfb` after Selection Day if not waiting for the 2026-12-07 10:00 UTC cron.
- [ ] **Step 8:** After the first post-merge crons: `python -m app.jobs.coverage --sport cfb` and `--sport nfl` (read-only) show 0 gaps; load `/cfb` and check the default slate and Week 14.

---

## Phase E: Release 2 (v1.3.1), the booth

### Task 14: Fact sheet occasion, stakes, records, last meeting

**Files:**
- Modify: `backend/app/services/fact_sheet.py:53-84,294-381,523-555`, `backend/app/services/predictions.py:234-272`
- Test: `backend/tests/test_fact_sheet.py`, `backend/tests/test_record.py`

**Interfaces:**
- Produces: `GameFacts` + `occasion: str | None = None`, `stakes: str | None = None`; `TeamFacts` + `seed: int | None = None`, `postseason_record: str | None = None`; `predictions.record_string` counts regular-season games only; new `postseason_record_string(games, team_id) -> str | None`; sheet lines "Occasion: ..." and "Stakes: ...".
- [ ] **Step 1: Failing tests:** occasion lines for Wild Card ("AFC Wild Card playoff game"), Super Bowl ("Super Bowl LXI, neutral site"), Rose Bowl QF with seeds ("Rose Bowl, College Football Playoff quarterfinal, No. 3 seed versus No. 6 seed, neutral site"), a bowl ("Pop-Tarts Bowl, neutral site"), a title game ("SEC Championship"); stakes "Win and advance; lose and the season ends" for NFL playoffs and CFP rounds except the finals ("Winner is the national champion" / "Winner wins the Super Bowl"), none for bowls and conference title games; `_matchup_note` uses the occasion for postseason instead of "interconference"/"X at Y"; records "13-4" plus postseason "1-0"; last meeting "in the 2025 Rose Bowl" and "in the 2025 NFL postseason"; no feed text reaches the sheet except through `_clean`.
- [ ] **Step 2-4:** Run, implement, run `tests/test_fact_sheet.py tests/test_record.py` then the full suite.
- [ ] **Step 5:** Commit `feat(booth): occasion, stakes and split records on the fact sheet`.

### Task 15: Guardrail seed rule and template opener

**Files:**
- Modify: `backend/app/services/narrate.py:172-190,1020-1150`, `backend/app/services/fallback_narration.py:54-75`
- Test: `backend/tests/test_narrate.py`, `backend/tests/test_fallback_narration.py`

**Interfaces:**
- Produces: `_SEED_RE` matching "No. 5 seed", "5 seed" and "5-seed" (spelled-out numbers are already rejected by the existing number-word rule). Every seed claim must equal a seed on the sheet; `_RANK_RE` matches followed by "seed" are skipped by the rank rule.
- [ ] **Step 1: Failing tests:** seed claim matching the sheet passes; wrong seed fails; seed claim in an NFL game fails (no seeds); "No. 7" rank claim still checked as a rank; capitalized occasion words ("Super Bowl", "Rose Bowl", "Quarterfinal", "CFP", "LXI") pass when on the sheet and fail when not; template opener "In the Rose Bowl, ..." and "In Super Bowl LXI, ..." and unchanged regular-season opener.
- [ ] **Step 2-4:** Run, implement, run both files then the full suite.
- [ ] **Step 5:** Commit `feat(booth): check seed claims and open postseason templates with the occasion`.

### Task 16: Ship Release 2

- [ ] **Step 0:** `test_spec_traceability.py`: `PENDING` is empty; replace `test_release_1_complete` with `test_all_requirements_traced` asserting `PENDING == set()`.
- [ ] **Step 1:** CHANGELOG, DECISIONS, narration-boundary diagram (seed rule, occasion line), footers `reflects v1.3.1`, `package.json` 1.3.1.
- [ ] **Step 2:** Full suites, lint, build; whole-branch code review plus a security pass focused on the new feed-text path (`event_name` and `notes` into the fact sheet and prompt).
- [ ] **Step 3:** PR, checks, merge outside 09:00 to 10:00 UTC, tag + GitHub release v1.3.1 before 2026-12-12.
- [ ] **Step 4 (go-ahead needed, paid):** after the next CFB cron, `python -m app.jobs.narration_eval --sport cfb --week 17 --stored` and for championship week 14; report pass rates to the maintainer.
- [ ] **Step 5:** Before 2027-01-16, read-only check that NFL Wild Card rows arrive and the default flips (`python -m app.jobs.coverage --sport nfl`). No code change expected.
