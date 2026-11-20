# Postseason Support: Design Spec

**Status:** approved 2026-11-19 (revision 2: detailed, requirement IDs, real-data appendix). Planning only; nothing built yet.
**Plan:** `docs/superpowers/plans/2026-11-19-postseason.md`
**Releases:** v1.3.0 (data, API, UI) merged by **2026-12-03**; v1.3.1 (booth) by **2026-12-12**.

**Maintainer decisions (2026-11-19):**
- Postseason sits behind a Regular season / Postseason toggle, shown as a segmented pill below the banner.
- Conference championships stay in the regular season as Week 14, labeled "Champ", and must stay visible.
- The CFP rounds and non-CFP bowls are the postseason.
- Last season's postseason data was checked read-only (Phase 0).
- The agent's recommendation applies on every other gap.

## How this spec lives in the code

- Every testable requirement has an ID: `PS-<area><n>`, e.g. `PS-C4`. Areas:
  - D data model, N NFL ingest, C CFB ingest, O odds/injuries
  - M model/features, J jobs, A API, F frontend
  - V championship visibility, B booth (narration)
- **A test that proves a requirement cites its ID** in its docstring (Python) or its `it(...)`/`describe(...)` title (Jest), e.g. `"""PS-C4: postseason upserts overwrite kickoff, venue and event."""`.
- **`backend/tests/test_spec_traceability.py`** parses every `PS-…` ID in this file and fails if any ID is missing from all of the following: `backend/tests/**/*.py`, `frontend/src/**/__tests__/**`, `frontend/src/**/*.test.*`. Adding a requirement without a test, or deleting the only test of one, breaks the build.
- `backend/app/postseason.py` opens with a one-line docstring pointing here. CLAUDE.md links this spec and carries the two invariants in §11. Product code carries no requirement IDs (CLAUDE.md: comments minimal).
- Checks that cannot be automated have IDs of the form `MC-<n>` (manual check). They sit next to the requirements they verify, are tracked in the plan, and are not enforced by the traceability test.
- During the build, the traceability test keeps an explicit `PENDING` set of IDs not yet implemented. Each task removes its IDs as it lands, and the test fails if a pending ID already has a test (forgot to remove) or a non-pending ID has none. At the end of Release 1 only `PS-B*` may be pending; at the end of Release 2 the set is empty.
- Real feed samples from Phase 0 (Appendix A) are committed as test fixtures under `backend/tests/fixtures/`. Tests run against real shapes, not invented ones.

## 1. Intent

The 2026 regular seasons end soon (CFB 2026-12-05/12; NFL 2027-01-10). Blitzcast must show, predict, narrate and grade every FBS and NFL postseason game as the matchups are announced, labeled as what they are ("AFC Wild Card", "Rose Bowl, CFP Quarterfinal", "Super Bowl LXI"), with no hand entry of matchups, times or venues. The data arrives from the existing feeds (nflverse, CFBD, The Odds API), and the site renders it correctly the moment it lands.

**Goals**
- Every postseason game appears, is predicted, narrated and graded within one cron cycle of the feed publishing it.
- Every visible label names the occasion.
- The UI looks intentional before, during and after each round.
- The regular season does not regress.

**Non-goals (this season)**
- No model retrain, and `MODEL_VERSION` 1.0.0 / cfb-1.0.0 stays unchanged.
- No bracket view and no TBD placeholder cards.
- No FCS, D-II, D-III, Celebration Bowl or all-star games.
- No NFL seeds.
- No historical CFB postseason backfill.

**Anti-goals (failure even if it works)**
- Any feature for game G using data from at or after G's kickoff.
- A wrong round, bowl, seed or favorite named anywhere.
- A bowl under September's Week 1.
- Daily Claude spend on games weeks away.
- A second rule home next to `market.py`, `isGameId` or `_clean()`.

## 2. Calendar and formats (researched 2026-11-19)

| Sport | Event | Date(s), ET | Feed shape |
|---|---|---|---|
| CFB | Conference championships (10 FBS) | Fri 12-04, Sat 12-05 | CFBD regular, **week 14**, notes "<Conf> Championship" |
| CFB | CFP Selection Day | Sun 12-06 noon | bracket, bowls and times set; rows appear after |
| CFB | Army-Navy | Sat 12-12 3pm, MetLife | regular week 15, neutral |
| CFB | Non-CFP bowls (32 to 41) | 12-15 to 01-02 | postseason week 1, `playoff` null |
| CFB | CFP first round (4) | Fri 12-18 8pm; Sat 12-19 noon, 3:30, 7:30 | on campus, higher seed home, **not neutral** |
| CFB | CFP quarterfinals | Wed 12-30 7:30 (Fiesta); Fri 01-01 noon/4/8 (Rose, Cotton, Peach) | neutral; which bowl gets which window is set on Selection Day |
| CFB | CFP semifinals | Thu 01-14 (Orange), Fri 01-15 (Sugar), 7:30 | neutral |
| CFB | CFP National Championship | Mon 01-25 7:30, Allegiant (indoor) | neutral |
| NFL | Week 18 | Sat 01-09, Sun 01-10 | times placeholder until ~01-03 |
| NFL | Wild Card (6) | 01-16 to 01-18 | week 19, `WC` |
| NFL | Divisional (4) | 01-23/24 | week 20, `DIV` |
| NFL | Conference Championships (2) | 01-31 | week 21, `CON` |
| NFL | Super Bowl LXI | Sun 02-14 6:30pm, SoFi (indoor) | week 22, `SB`, Neutral, NFC champion is designated home |

**CFP format (2026-27)**
- This is the last 12-team year.
- Automatic bids go to the ACC, Big Ten, Big 12 and SEC champions, plus the highest-ranked G6 team, which no longer has to be a champion. The remaining seven bids are at-large.
- Notre Dame is in automatically with a top-12 finish.
- Seeding is straight; seeds 1-4 get byes.
- The bracket is fixed, with no reseeding.
- Seeds 1-3 pick their quarterfinal bowl in order.

**NFL format (2026-27)**
- 14 teams, and only the 1 seed gets a bye. No seeding change was adopted.
- The Rams are LXI's financial host. The designated home team is the NFC champion (conferences alternate; LX's home team was AFC).
- There is no Pro Bowl game.

**Other**
- Committee rankings come out on Tuesdays until 12-01; the final ranking is on 12-06.
- The January transfer portal window opens right after New Year's, which drives bowl opt-outs.
- **2027:** the CFP goes to 24 teams with two on-campus rounds, Power Four title games are expected to end, Army-Navy moves to 2027-12-04, and the title game is 2028-01-24.

## 3. Today's code (main 31d2db5, v1.2.6)

**Works:**
- NFL weeks 19-22 are ingested.
- The NFL strip and default are data-driven.
- NFL playoffs are already in Elo, training and backtests.
- Crons cover Jan (CFB) and Feb (NFL).
- Season rollover puts Jan/Feb games in season 2026.
- The record counts postseason games.
- TBD kickoffs render everywhere.
- Game ids fit `isGameId`.

**Broken or missing:**
1. CFB postseason is never ingested: every CFBD call defaults to `seasonType="regular"`, and the miss is silent.
2. No `season_type` or `round` exists anywhere.
3. Loading CFBD postseason rankings would put the final poll into features (leakage).
4. The CFB strip is hard-coded 1 to 15 (2025 reached week 16), and its default sticks on 15.
5. Rounds render as bare week numbers.
6. Neutral sites still say "@" / "at".
7. Narration:
   - The Super Bowl is described as "interconference" and bowls as "X at Y".
   - Seeds are read as poll ranks.
   - Playoff records include playoff games.
8. Odds matching only works in one home/away orientation.
9. A month-long postseason slate would get Claude calls daily.
10. Smaller items:
    - The "Divisional" badge clashes with the round name.
    - The Super Bowl gets an outdoor forecast.
    - One bad NFL row aborts the whole sync.
    - TBD-time games get no injuries.

## 4. Approach (chosen) and alternatives

**Chosen:** add `season_type`, `round`, `event_name` and seed columns to `games`.
- NFL keeps weeks 19-22.
- CFB postseason games are stored at **slate week 17** (`CFB_POSTSEASON_WEEK`), past any regular week CFBD has used (16 in 2025). Every existing `(season, week)` query stays collision-free.
- Labels and logic come only from `season_type`/`round`.
- The UI is a Regular season / Postseason toggle with round chips. A CFB postseason chip filters week 17 by round.

**Rejected:**
- **Keeping CFBD's raw week 1 and adding `season_type` to every week-keyed query:** about 15 call sites, two keys, and one miss silently mixes bowls into Week 1.
- **Frontend-only mapping of week numbers to rounds:** CFB rounds can't be told apart by week, and the booth and API stay blind.
- **One combined CFB postseason slate:** replaced by the maintainer's toggle.

## 5. Data model

- **PS-D1** `games` gains:
  - `season_type` (String(12), NOT NULL, default and server default `'regular'`)
  - `round` (String(24), NULL)
  - `event_name` (String(64), NULL)
  - `home_seed` and `away_seed` (SmallInteger, NULL)

  A new Game defaults to regular with a NULL round.
- **PS-D2** Database CHECK constraints:
  - `season_type IN ('regular','postseason')`
  - `round` NULL or one of `conf_championship, wild_card, divisional, conference, super_bowl, bowl, cfp_first_round, cfp_quarterfinal, cfp_semifinal, cfp_championship, cfp_other`

  Unknown values raise `IntegrityError`.
- **PS-D3** The migration (down_revision `c3f1a9d27e48`) backfills NFL history as postseason, with rounds by week:
  - 2021 onward: 19 to 22
  - before 2021: 18 to 21

  Super Bowls also get `event_name`. Upgrade, downgrade and upgrade again all run cleanly.
- **PS-D4** `backend/app/postseason.py` is the only place that maps game types, playoff rounds, slugs and labels, or cleans event names. No other module derives a round from a week number.
- **PS-D5** The constants in Appendix B (round values, slugs, labels, `CFB_POSTSEASON_WEEK = 17`) are defined once in `postseason.py`. The frontend `Round` type lists the same 11 values.

## 6. Ingestion

### NFL (`games_loader.py`)
- **PS-N1** `game_type` maps to `season_type`/`round`:

  | `game_type` | `season_type` | `round` |
  |---|---|---|
  | REG | regular | NULL |
  | WC | postseason | wild_card |
  | DIV | postseason | divisional |
  | CON | postseason | conference |
  | SB | postseason | super_bowl |

  A row with any other `game_type` is skipped and logged.
- **PS-N2** `event_name` is "{AFC|NFC} Wild Card", "{AFC|NFC} Divisional", "{AFC|NFC} Championship" (the home team's conference), or `super_bowl_name(season)`. 2026 gives "Super Bowl LXI" (numeral = season - 1965).
- **PS-N3** For neutral rows, `is_neutral_site` and `venue_name` stay as today. `stadium_id` is also linked when nflverse's `stadium` name exactly matches a `Stadium.name` ("SoFi Stadium" is in the seed), so weather says indoors. An unmatched name keeps `stadium_id` NULL.
- **PS-N4** A row with an unresolvable team, a missing `gameday` or a bad type is logged as `skipped NFL row <game_id>: <reason>` and skipped. The rest of the sync completes.

### CFB (`cfbd.py`, `cfb_games_loader.py`, `refresh_schedule_cfb.py`, `refresh_stats_cfb.py`)
- **PS-C1** The schedule sync fetches `seasonType=regular` and `seasonType=postseason` (with `classification=fbs`). A postseason row is kept only when both `homeClassification` and `awayClassification` are `fbs`. FCS, D-II, D-III and Celebration Bowl rows are skipped.
- **PS-C2** A postseason row is stored with:
  - `season_type='postseason'` and `week=17`
  - `round` = `cfb_playoff_round(playoff.round)` when `playoff` exists, else `bowl`
  - seeds from `playoff.homeSeed` / `playoff.awaySeed`
- **PS-C3** An unknown `playoff.round` (e.g. 2027's new rounds) is stored as `cfp_other` and logged once. It is never dropped.
- **PS-C4** Every upsert overwrites kickoff, venue, `stadium_id`, neutral flag, `round`, `event_name` and seeds, because Selection Day assigns bowls, times and campus sites after a row can already exist.
- **PS-C5** Event names (rules in Appendix C):
  - A CFP game uses `cfp_event_name(round, bowlName)`.
  - A bowl uses `clean_event_name(notes)`, falling back to "Bowl game".
  - No stored `event_name` ever contains U+2013 or U+2014.
- **PS-C6** A regular-season row is a conference championship when `notes` contains "championship" (case-insensitive) and both teams' conferences are equal and non-null. It then gets `round='conf_championship'` and `event_name` = cleaned notes (e.g. "SEC Championship"). CFBD `conferenceGame` is never used: it is False for all 2025 title games.
- **PS-C7** A game whose championship detection fails is still stored and shown in its week. Detection only adds the round, the label and the badge.
- **PS-C8** A regular-season row with `week >= 17` is logged as an error and skipped, so it can never mix into the postseason slate.
- **PS-C9** The team-game stats refresh also pulls postseason PPA, so later CFP rounds see earlier results. Elo picks up postseason results through its existing replay.
- **PS-C10** `load_rankings` is only ever called for the regular season. A test inspects every call site in `data_pipeline/`.
- **PS-C11** Run against the committed real 2025 fixture, the loader stores exactly:
  - 46 FBS games at week 17
  - 11 with a CFP round, all with both seeds
  - first-round games not neutral
  - the Hawai'i Bowl not neutral (a home game)
  - no dash in any `event_name`

  Against the week-15 fixture, all 9 title games get `conf_championship`.

### Odds and injuries
- **PS-O1** If an odds event matches no game in the stored orientation, the swapped team pair is tried, **only for games with `is_neutral_site`**. On a swap, the spread sign flips and the moneylines swap before writing. `market.py` stays the only plausibility rule.
- **PS-O2** A non-neutral game never matches in swapped orientation.
- **PS-O3** When both orientations could match, the exact orientation wins.
- **PS-O4** A game with a NULL kickoff receives injuries when its `game_date` is today or later.
- **MC-1** Before merging, count how many neutral regular-season games gain an odds match (dry run, local database). Record the count in the CHANGELOG.

## 7. Model, features, jobs

- **PS-M1** CFB rank display, `ranks_for_week` and the features poll join use the **latest regular-season poll** in the table (AP preferred) for every postseason game. A postseason poll is never read.
- **PS-M2** A PollRank row filed under a postseason week (the final poll, published after the title game) never reaches a postseason game's features or display.
- **PS-M3** CFB `week_number` is clamped to 16 for postseason rows. NFL week numbers are unchanged. No other feature changes; the model artifacts are untouched.
- **PS-J1** `predict_week` targets every unplayed, published postseason game of the season on every run, regardless of the 7-day window. Postseason games never sit at "Prediction pending" for weeks.
- **PS-J2** Claude narrates only games whose kickoff (or `game_date` when TBD) is within `LOOKAHEAD_DAYS` (7). Games further out get `fallback_narration` and count as `fallback`. Near-even games keep their template path.
- **PS-J3** `coverage` expects a prediction and a booth for every unplayed, published postseason game.
- **PS-J4** `default_week` and the summary line format are unchanged for the regular season.
- No cron changes. The crons are verified to cover Aug to Jan (CFB, 10:00 UTC) and Sep to Feb (NFL, 09:00 UTC).

## 8. API

All five places per CLAUDE.md change in one go: `schemas.py`, `services/predictions.py`, `mock_data.py`, `types.ts` (nullability exact), and `mock.ts` + `mockCfb.ts`. All are asserted in `api.test.ts`.

- **PS-A1** `GameSummary` gains:
  - `season_type: "regular" | "postseason"`
  - `round: Round | null`
  - `event_name: string | null`
  - `is_neutral_site: boolean`
  - `home_seed: number | null`, `away_seed: number | null`

  `MatchupDetail` gains the same fields except `is_neutral_site`, which already lives in `venue`.
- **PS-A2** `GET /api/slates?season=2026&sport=NFL|CFB` returns `Slate[]` (shape in Appendix D):
  - It is unfiltered by status and cached 60 s like `/api/schedule`.
  - Order: regular weeks ascending, then postseason slates in round order.
  - NFL weeks 19-22 are postseason slates keyed by slug.
  - CFB week 17 splits into one slate per round present.
- **PS-A3** A regular slate has key `w{N}`, `group_label` "Wk" and `short_label` "{N}". A regular week containing at least one `conf_championship` game instead has `label` "Conference Championships" and `group_label` "Champ". This holds even if the week also has a non-championship game.
- **PS-A4** For each slate:
  - `next_kickoff` is the earliest kickoff later than now minus 12 hours.
  - `has_unscheduled` is true when any game has a NULL kickoff and no scores.
  - `first_kickoff` and `last_kickoff` span the slate.
- **PS-A5** `GET /api/games` accepts an optional `round` (slug, `^[a-z-]{1,24}$`). `week=17&round=bowls` returns only bowls, and an unknown slug returns 422.
- **PS-A6** Mock mode returns at least one postseason slate per sport, with the fixtures listed in Appendix D.

## 9. Frontend

- **PS-F1** `pickDefaultSlate(slates, now)`:
  1. If any postseason slate exists, the candidates are postseason slates only. Otherwise every slate is a candidate.
  2. A slate is live when `next_kickoff` is set or `has_unscheduled` is true.
  3. Among live candidates, a slate whose round starts with `cfp_` and whose `next_kickoff` is within 7 days wins (soonest first).
  4. Otherwise the live slate with the smallest `next_kickoff` wins. Slates with only unscheduled games sort after dated ones.
  5. If nothing is live, the last candidate wins.
- **PS-F2** The default-slate results in Appendix E hold exactly, for both sports.
- **PS-F3** `resolveSlate(slates, {week, round}, now)`:
  - `?week=N` opens that regular week even when postseason exists.
  - `?round=<slug>` opens that postseason slate.
  - Unknown values, a postseason week typed as `?week=17`, or a slug from the other sport fall back to the default.
- **PS-F4** `PhaseToggle` renders nothing until a postseason slate exists. Its two links go to the phase's default slate. When Postseason is the inactive side, it shows a gold dot. It reuses the StatusFilter `on`/`off` classes and sits on its own row below the banner.
- **PS-F5** `SlateSelector` (formerly WeekSelector):
  - It shows only the active phase's slates.
  - Each chip is `group_label` over `short_label`.
  - Links are `?week=N` or `?round=slug`, with prefetch off.
  - The active chip has `aria-current="page"` and is scrolled into view.
  - The strip heading reads "Select a week" or "Select a round".
- **PS-F6** The banner eyebrow comes from `eyebrowText(season, slate)` (copy in Appendix F).
- **PS-F7** `GameCard`:
  - It shows the event badge (Prime time pill style plus a gold tint) when `event_name` is set.
  - A CFP seed shows as "(5)" in place of the AP rank. Bowls keep "#N".
  - Regular games are unchanged.
- **PS-F8** Matchup page:
  - The hero eyebrow is `event_name`, falling back to "Week N".
  - The center mark is "vs" for neutral sites.
  - The metadata title and description and the OG footer use `matchupTitle` and the occasion.
  - The back link comes from `backLink` (copy in Appendix F).
  - `Disagreements` uses "vs" for neutral games.
- **PS-F9** The NFL same-division badge reads "Division game". The SHAP label "Divisional rivalry game" becomes "Division rivalry game" (`ml/explain.py`, `mock_data.py`).
- **PS-F10** The conference and Top 25 filter chips show on regular weeks and on the `bowls` slate only. StatusFilter and FilterChips links keep `week=N` or `round=slug`.
- **PS-F11** No new visitor-visible string (Appendix F, badges, How It Works paragraph, empty state) contains U+2013, U+2014, `&mdash;` or `&ndash;`.
- **PS-F12** `CFB_WEEKS`, `pickCfbDefaultWeek` and `pickDefaultWeek` are removed. Both sports use slates.
- **PS-F13** A published slate with zero games shows "Matchups are set as each round is decided."

## 9b. Conference championships stay visible (maintainer requirement)

- **PS-V1** From 2026-12-01 until the title games are played, `/cfb` opens on Week 14 with the eyebrow "2026 Season · Conference Championships". This is covered by the Appendix E table.
- **PS-V2** After postseason slates exist, the Regular season side still lists Week 14 as "Champ / 14", and `/cfb?week=14` opens it directly.
- **PS-V3** Each championship card shows its event badge, and its matchup page names the game.
- **MC-2** Before 2026-12-04, a read-only production query confirms that the 10 2026 title games sit in Week 14 with `round='conf_championship'`.

## 10. Narration (Release 2)

- **PS-B1** `GameFacts.occasion` is built only from our own fields (copy in Appendix F). Examples:
  - "AFC Wild Card playoff game"
  - "Super Bowl LXI, neutral site"
  - "Rose Bowl, College Football Playoff quarterfinal, No. 3 seed versus No. 6 seed, neutral site"
  - "Pop-Tarts Bowl, neutral site"
  - "SEC Championship"
- **PS-B2** `GameFacts.stakes`:
  - NFL playoff rounds before the Super Bowl and CFP rounds before the title game: "Win and advance; lose and the season ends".
  - Super Bowl: "Winner wins the Super Bowl".
  - CFP title game: "Winner is the national champion".
  - Bowls and conference title games: none.
- **PS-B3** For postseason games, the matchup note is the occasion, never "interconference" or "X at Y".
- **PS-B4** `record_string` counts regular-season games only. `TeamFacts.postseason_record` carries the playoff record separately (e.g. "13-4", plus "1-0").
- **PS-B5** Last meeting reads "in the 2025 Rose Bowl" or "in the 2025 NFL postseason", based on the prior game's `season_type`/`event_name`. It never reads "Week 17".
- **PS-B6** `check_narration` seed rule:
  - "No. N seed", "N seed" and "N-seed" must equal a seed on the sheet.
  - Rank matches followed by "seed" skip the rank rule.
  - An NFL seed claim fails, because NFL sheets carry no seeds.
  - Occasion words ("Super Bowl", "Rose Bowl", "Quarterfinal", "CFP", "LXI") pass only when they are on the sheet.
- **PS-B7** Fallback opener: "In the Rose Bowl, ..." and "In Super Bowl LXI, ...". The regular-season opener is unchanged.
- **MC-3** After the first postseason cron following Release 2, run `narration_eval --stored` for CFB weeks 14 and 17. This is paid and needs the maintainer's go-ahead.

## 11. Invariants added to CLAUDE.md

1. Postseason identity comes from `Game.season_type` / `Game.round`, never from week arithmetic. CFB postseason games live at slate week 17 (`CFB_POSTSEASON_WEEK`), and `app/postseason.py` is the only place that maps rounds.
2. CFBD postseason rankings are never loaded: the final poll, published after the title game, is filed as postseason week 1. Postseason games read the latest regular-season poll.
3. The neutral-site rule is updated: a neutral NFL game links `stadium_id` when the venue name matches a known stadium.

## 12. Delivery and manual checks

- Release 1 (v1.3.0, by 2026-12-03): §5 to §9b. Release 2 (v1.3.1, by 2026-12-12): §10.
- Each production write or paid call needs the maintainer's go-ahead at the time:
  - the production migration
  - a manual CFB sync after Selection Day (otherwise the 2026-12-07 10:00 UTC cron picks the games up)
  - re-predicts
  - `narration_eval`
- **MC-4** Before merge, review a mock-mode production build in Chrome:
  - light and dark themes, phone width
  - both sports and both phases, every chip
  - a matchup page and an OG image
- **MC-5** After the first post-merge crons, read-only `coverage --sport cfb|nfl` shows 0 gaps.
- Each release updates:
  - CHANGELOG, DECISIONS, CLAUDE.md and the READMEs (drop the "no CFB postseason" limitation)
  - the diagrams (schema ER, pipeline, prediction read path, narration boundary) and their footers
  - the `package.json` version
  - the GitHub release
- Merge outside 09:00 to 10:00 UTC. No attribution lines in commits or PRs.

## 13. Known limits (documented, not fixed this season)

- Elo applies home-field advantage at neutral sites, and the 1.0 models have no neutral feature. The posted market line dampens this.
- Bowl opt-outs, interim coaches and motivation are not modeled. The market line is shown beside the model.
- "Neutral" games in a team's own stadium (Rams at SoFi, Boise State at the Potato Bowl) follow the feed's label.
- The CFB model never trained on bowls. NFL playoff rows are thin in training (about 13 per season).
- Placeholder behavior before matchups are announced can't be seen in historical data. Unresolvable rows are skipped, which is safe either way.

## 14. Off-season follow-ups

- A bracket view, from CFBD `/playoffs/cfp` (its bracket, seeds and slot sources are already in the 2025 sample).
- A CFB postseason backfill (2021 to 2025) and neutral-site features in the P4 retrain.
- 2027's 24-team rounds: label the new CFBD `playoff.round` values (stored as `cfp_other` until then).

---

## Appendix A: real feed samples (Phase 0, 2026-11-19, read-only)

Raw files: `backend/tests/fixtures/cfbd_post_2025.json` (46 FBS rows plus 3 non-FBS), `cfbd_reg_2025_w15.json` (9 title games) and `nflverse_playoffs_2025.csv` (13 rows). They were trimmed from 8 CFBD calls and the nflverse `games.csv`.

**nflverse playoff row (Super Bowl LX):**
```
game_id=2025_22_SEA_NE season=2025 game_type=SB week=22 gameday=2026-02-08 gametime=18:30
away_team=SEA home_team=NE location=Neutral stadium_id=SFO01 stadium="Levi's Stadium"
roof=outdoors away_rest=14 home_rest=14 spread_line=-4.5 away_moneyline=-238 home_moneyline=195
```
- Weeks 19-22 map to WC/DIV/CON/SB.
- The file has never contained a TBD team.
- A playoff row appears 0 to 3 hours after the deciding game, and odds follow within about 12 hours.

**CFBD CFP quarterfinal (abridged):**
```json
{"season":2025,"week":1,"seasonType":"postseason","startDate":"2026-01-01T...","startTimeTBD":false,
 "neutralSite":true,"conferenceGame":false,"venue":"Rose Bowl","homeTeam":"Indiana","awayTeam":"Alabama",
 "homeClassification":"fbs","awayClassification":"fbs",
 "notes":"College Football Playoff Quarterfinal at the Rose Bowl Presented by Prudential",
 "playoff":{"competition":"cfp","format":"twelve_team_2025","round":"quarterfinal","roundName":"Quarterfinal",
            "bracketSlot":"QF..","homeSeed":1,"awaySeed":9,"bowlName":"Rose Bowl"}}
```
- First round: `neutralSite:false`, a campus venue, the higher seed at home, `bowlName` "College Football Playoff First Round Game".
- Title game: `bowlName` "College Football Playoff National Championship Presented by AT&T".

**CFBD non-CFP bowl:** `playoff:null`, with the official sponsored name in `notes`:
- "Union Home Mortgage Gasparilla Bowl"
- "Bad Boy Mowers Pinstripe Bowl"
- "68 Ventures Bowl"
- "IS4S Salute to Veterans Bowl"
- "Sheraton Hawaiʻi Bowl" (U+02BB okina; `neutralSite:false` because Hawai'i hosted)

The longest note is 39 characters, and no FBS note contains an en or em dash.

**CFBD conference championship (2025 regular week 15):** `notes:"SEC Championship"`, both conferences "SEC", `conferenceGame:false`, `neutralSite:true` at Mercedes-Benz Stadium. Hosted title games (Sun Belt, CUSA, American, MW) are `neutralSite:false`.

**Other findings:**
- The 2025 postseason call returned 86 rows: 46 fbs/fbs, plus fcs, ii and iii rows (FCS and D-II/III playoffs at weeks 1, 13 and 14).
- The CFBD 2026 calendar puts week 14 at 11-30 to 12-07, week 15 at 12-07 to 12-12, and postseason week 1 at 12-12 to 01-28.
- `/rankings` postseason week 1 holds the final AP and Coaches polls (the PS-M2 trap).
- Every CFBD venue, domes included, is upserted into `stadiums` by `seed_cfb` with `is_dome`, so name matching resolves bowl venues.

## Appendix B: constants (`app/postseason.py`)

| round | season_type | slug | label (eyebrow) | group | short |
|---|---|---|---|---|---|
| conf_championship | regular | (none; it is week 14) | Conference Championships | Champ | (week no.) |
| wild_card | postseason | wild-card | Wild Card | Round | WC |
| divisional | postseason | divisional | Divisional | Round | DIV |
| conference | postseason | conference | Conference Championships | Round | CONF |
| super_bowl | postseason | super-bowl | Super Bowl | Round | SB |
| bowl | postseason | bowls | Bowl Season | Non-CFP | Bowls |
| cfp_first_round | postseason | cfp-first-round | CFP First Round | CFP | R1 |
| cfp_quarterfinal | postseason | cfp-quarterfinals | CFP Quarterfinals | CFP | QF |
| cfp_semifinal | postseason | cfp-semifinals | CFP Semifinals | CFP | SF |
| cfp_championship | postseason | cfp-title | National Championship | CFP | Title |
| cfp_other | postseason | cfp-other | College Football Playoff | CFP | CFP |

- `SEASON_REGULAR="regular"`, `SEASON_POSTSEASON="postseason"`, `CFB_POSTSEASON_WEEK=17`, `NFL_GAME_TYPES=("REG","WC","DIV","CON","SB")`.
- Postseason slate order is the table order above.

## Appendix C: event-name rules

| Input | `event_name` |
|---|---|
| NFL WC, home AFC | AFC Wild Card |
| NFL DIV, home NFC | NFC Divisional |
| NFL CON, home AFC | AFC Championship |
| NFL SB, season 2026 | Super Bowl LXI |
| CFP quarterfinal, bowlName "Cotton Bowl" | Cotton Bowl, CFP Quarterfinal |
| CFP semifinal, bowlName "Orange Bowl" | Orange Bowl, CFP Semifinal |
| CFP first round, bowlName "College Football Playoff First Round Game" | CFP First Round |
| CFP championship, bowlName "...National Championship Presented by AT&T" | CFP National Championship |
| CFP unknown round | College Football Playoff |
| Bowl, notes "Sheraton Hawaiʻi Bowl" | Sheraton Hawai'i Bowl |
| Bowl, notes "Pop-Tarts Bowl presented by Kellogg" | Pop-Tarts Bowl |
| Bowl, notes "Rose Bowl Game – CFP Quarterfinal" (en dash) | Rose Bowl Game, CFP Quarterfinal |
| Bowl, notes null or junk ("Bowl 2026-27 Game 12345", over 48 chars, a URL) | Bowl game |
| Regular, notes "SEC Championship", both SEC | SEC Championship |

`clean_event_name` steps, in order:
1. Run `fact_sheet._clean(raw, 64)`.
2. Map U+02BB, U+2018 and U+2019 to `'`.
3. Replace U+2013/U+2014 with ", ".
4. Drop a trailing `(presented|powered|hosted) by ...`.
5. Collapse spaces.
6. Accept only `^[A-Za-z0-9'&.,\- ]{3,48}$` with at most 2 digits; otherwise return None.

`cfp_event_name` uses the bowl only when the cleaned `bowlName` ends in "Bowl".

## Appendix D: API shapes

```json
// GET /api/slates?season=2026&sport=CFB (excerpt)
[
 {"key":"w14","phase":"regular","week":14,"round":null,"label":"Conference Championships",
  "group_label":"Champ","short_label":"14","game_count":10,
  "first_kickoff":"2026-12-05T00:00:00Z","next_kickoff":null,"has_unscheduled":false,
  "last_kickoff":"2026-12-06T01:00:00Z"},
 {"key":"bowls","phase":"postseason","week":17,"round":"bowl","label":"Bowl Season",
  "group_label":"Non-CFP","short_label":"Bowls","game_count":37,"first_kickoff":"2026-12-15T23:00:00Z",
  "next_kickoff":"2026-12-22T17:30:00Z","has_unscheduled":true,"last_kickoff":"2027-01-02T23:00:00Z"},
 {"key":"cfp-quarterfinals","phase":"postseason","week":17,"round":"cfp_quarterfinal",
  "label":"CFP Quarterfinals","group_label":"CFP","short_label":"QF","game_count":4,"...":"..."}
]

// GameSummary (CFP quarterfinal)
{"game_id":"cfb_401999001","sport":"CFB","kickoff":"2027-01-01T21:00:00Z",
 "home":{"abbr":"ORE","name":"Oregon","rank":3,"...":"..."},"away":{"abbr":"ND","name":"Notre Dame","rank":6},
 "season_type":"postseason","round":"cfp_quarterfinal","event_name":"Rose Bowl, CFP Quarterfinal",
 "is_neutral_site":true,"home_seed":3,"away_seed":6,"is_primetime":false,"status":"scheduled",
 "has_prediction":true,"home_win_prob":0.57,"market_home_prob":0.55,
 "home_score":null,"away_score":null,"prediction_correct":null}
```

Mock fixtures (PS-A6):
- NFL weeks 19-22, including a neutral Super Bowl at SoFi.
- CFB Week 14 with 2 title games.
- CFB week 17 with 2 bowls (one TBD kickoff), 2 first-round games and 1 quarterfinal, all with seeds.

## Appendix E: default slate on first load (PS-F2, PS-V1)

Uses the 2026-27 calendar fixtures; `now` is 15:00 UTC on each date.

| Sport | Date | Opens on |
|---|---|---|
| CFB | 2026-11-19 | Week 12 (no postseason yet; toggle hidden) |
| CFB | 2026-12-01 | Week 14, "Conference Championships" |
| CFB | 2026-12-08 | Bowls (postseason exists; CFP R1 is more than 7 days out) |
| CFB | 2026-12-14 | CFP R1 (within 7 days, beats Bowls) |
| CFB | 2026-12-21 | Bowls |
| CFB | 2026-12-26 | CFP Quarterfinals |
| CFB | 2027-01-04 | CFP Semifinals (no bowls left; soonest) |
| CFB | 2027-01-20 | National Championship |
| NFL | 2027-01-05 | Week 18 |
| NFL | 2027-01-12 | Wild Card |
| NFL | 2027-01-20 | Divisional |
| NFL | 2027-01-26 | Conference |
| NFL | 2027-02-03 | Super Bowl |

## Appendix F: visitor-visible copy (no em or en dashes)

| Where | Text |
|---|---|
| Toggle | Regular season · Postseason |
| Strip heading | Select a week · Select a round |
| Eyebrow | 2026 Season · Week 12 / 2026 Season · Conference Championships / 2026 Postseason · Wild Card / 2026 Postseason · CFP Quarterfinals |
| Empty published slate | Matchups are set as each round is decided. |
| Hero badge (NFL same division) | Division game |
| Matchup title | BUF vs DET, Super Bowl LXI / KC @ BUF, Week 5 |
| Back link | Back to Wild Card (`/nfl?round=wild-card`) / Week 5 slate (`/nfl?week=5`) |
| OG footer | Super Bowl LXI · 2026 / Week 5 · 2026 |
| Seed on card | (5) |
| Stakes (booth) | Win and advance; lose and the season ends / Winner wins the Super Bowl / Winner is the national champion |
| How It Works | One short paragraph: postseason games are often at neutral sites; bowl opt-outs and coaching changes aren't modeled, so the market line is shown beside every pick. |
