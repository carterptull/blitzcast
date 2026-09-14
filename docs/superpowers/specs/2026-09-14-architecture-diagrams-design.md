# Architecture diagrams + repo housekeeping (v1.0.10)

Date: 2026-09-14 · Status: approved design · Branch: `ct/docs/architecture-diagrams`

## Goal

Give Blitzcast hand-maintained Mermaid architecture diagrams that show how the system is
actually built (frontend, API, batch pipeline, ML, LLM boundary, schema, deployment), and
clean up the documentation drift found while exploring for them. One branch, one PR,
released as 1.0.10 (the maintainer cuts the GitHub release and tag manually after merge).

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Where diagrams live | Root `diagrams/`, linked from README and CLAUDE.md |
| Diagram set | All 10 below (plus an index `README.md`) |
| `cartertull.com` references | Keep the literal origin only in the `frame-ancestors` CSP value (functionally required); reword surrounding prose to "the maintainer's portfolio site"; add a CLAUDE.md carve-out naming the CSP value as the sole exception |
| Code/config fixes | All four: `npm test` in CI, pin Python deps, `next` 16.3.5, cron `$schema` URL |
| PR shape | One branch, one PR, version 1.0.10 |
| Side cleanup | Delete merged local branches, delete `next_steps.md` (backed up first), add `security.txt` |
| Commit identity | Carter Tull, no AI co-author or session trailers |

## Diagram set

Every file: short intro, one Mermaid block, 2-3 "why it's built this way" notes linking to
`DECISIONS.md`, footer `_Last updated: 2026-09-14 · reflects v1.0.10_`.

1. **`overview.md`** (flowchart): whole system in one picture, "Go deeper" table.
2. **`c4-context.md`** (flowchart styled as C4 L1): visitor, portfolio origin (embeds the app),
   nflverse, CollegeFootballData, The Odds API, Visual Crossing, ESPN (NFL injuries + logos),
   Anthropic; Cloudflare/Vercel/Railway as hosting.
3. **`c4-container.md`** (flowchart styled as C4 L2): Next.js on Vercel, FastAPI on Railway,
   `nfl-cron` (`0 9 * 9,10,11,12,1,2 *` UTC) and `cfb-cron` (`0 10 * 8,9,10,11,12,1 *` UTC),
   Postgres 16, committed
   model artifacts, GitHub Actions CI.
4. **`er-diagram.md`** (erDiagram): `stadiums`, `teams`, `games`, `team_game_stats`,
   `team_ratings`, `odds`, `weather`, `injuries`, `poll_ranks`, `predictions` with PK/FK/unique
   constraints. Notes: completion keyed on scores not `status`; `odds` holds one upserted
   snapshot per `(game_id, source)` with `captured_at` refreshed on each run, falling back to
   `games`' closing lines when absent; `predictions` unique on `(game_id, model_version)` and `backtest-*` rows
   are excluded from slate + record but shown (labeled) on the matchup page.
5. **`prediction-request-sequence.md`** (sequence): browser → Next server component
   (`revalidate = 30`) → `GET /api/predictions/{game_id}` → mock / 404 / pending / ready
   branches. The read path never runs the model.
6. **`llm-narration-boundary.md`** (flowchart): fixed model inputs → key gate → sport system
   prompt → Claude → `_plain_punctuation` → `_percentages_consistent` →
   `_favorite_attribution_consistent` → `_market_attribution_consistent` → accept, or retry once
   after 2s → `None` (factor list shown without prose). Shaded region marks what Claude cannot
   touch.
7. **`daily-refresh-sequence.md`** (sequence): Railway cron → orchestrator → subprocess steps
   (NFL vs CFB `alt`), soft-fail contract (only schedule-sync failure skips prediction),
   `predict_week` internals, idempotent per-game commits.
8. **`ml-pipeline.md`** (flowchart): train (2022-2024 train, 2025 Platt calibration,
   `assert_temporally_disjoint`, committed artifact), validate (walk-forward backtest,
   `backfill_predictions` → `backtest-*`), serve (`predict_week`).
9. **`game-lifecycle-state.md`** (stateDiagram-v2): Scheduled → Predicted → Final → Called it /
   Missed / Ungraded (tie, exact 0.5, no market probability).
10. **`deployment-security.md`** (flowchart): Cloudflare DNS → Vercel (DDoS mitigation and the
    prefetch-burst root cause, `frame-ancestors` CSP) → Railway API (CORS allowlist) → Postgres;
    secrets handling, CI gates, `security.txt`.

### Mermaid rules (learned from the portfolio repo)

- No native `C4Context`/`C4Container`; use `flowchart` styled like C4 levels.
- `classDiagram` relationship labels: single line, no colons (none planned here).
- `stateDiagram-v2` transition labels: plain single-line text, no `\n`.
- `flowchart` labels: use `<br/>` for breaks, never `\n`.
- Verification means viewing every rendered file on github.com, not reading the source.
- No em dashes in new user-visible text (`security.txt`); prefer plain punctuation in diagrams.

## Housekeeping

- **README.md:** version line → release badge; crons are daily not weekly; drop hardcoded test
  counts; link `diagrams/`.
- **SECURITY.md:** "Latest release" instead of a hardcoded version; `security.txt` renewal note.
- **CLAUDE.md:** routes (`/[sport]`, `/[sport]/matchup/[gameId]`, `/how-it-works`);
  `MODEL_VERSION` 1.0.0 / `cfb-1.0.0`; committed-artifact exception; diagrams pointer; branding
  carve-out; "no em dashes in user-visible text" rule carried over from `next_steps.md`.
- **backend/README.md:** committed-artifact exception; diagrams pointer.
- **`data_pipeline/backfill_cfb.py`:** usage docstring says `[--end 2025]`; the argparse default
  is 2026 (fixed in 1.0.1), so the docstring is the stale side.
- **Branding prose:** `frontend/next.config.ts` comment, `DECISIONS.md`, `CHANGELOG.md`.
- **CI:** add `npm test` to the frontend job.
- **Dependencies:** pin top-level `requirements.txt` packages with `==` to the versions
  production installed (Railway build log); if xgboost or scikit-learn differ from local, stop
  and ask. `next` + `eslint-config-next` → 16.3.5.
- **`railway-cfb-cron.json`:** `$schema` gets `https://`.
- **New `frontend/public/.well-known/security.txt`:** Contact (private advisory URL), Expires
  2027-09-14, Preferred-Languages en, Canonical for apex and `www`, Policy (SECURITY.md).
- **Version:** 1.0.10 in `frontend/package.json` + lockfile; CHANGELOG `[1.0.10]`. FastAPI
  `version="1.0.0"` is the API contract version and stays.
- **Local only:** delete merged `ct/*` branches (verified merged via PR state), prune remote
  refs, delete `next_steps.md` after backup.

## Out of scope (flagged)

- `predict_week` treats "both scores NULL" as unplayed, so a game in progress at cron time can
  be re-predicted with unchanged pre-kickoff inputs, restamping `predicted_at` after kickoff.
  Needs its own fix + tests.
- Cloudflare Bot Fight Mode / AI Labyrinth: dashboard toggles, maintainer's call; risk of
  challenging link-preview crawlers.

## Verification

1. Local: `ruff check .`, `pytest` (168), `npm test` (126), `npm run lint`, `npm run build`.
2. PR CI green via `gh pr checks --watch`.
3. Every diagram viewed rendered on github.com in Chrome.
4. Vercel preview: rapid week/sport switching shows no 503s; `/.well-known/security.txt` serves.
5. Railway: deploy with pinned deps builds and the API serves `/health` and a matchup.
6. Merge outside the 09:00/10:00 UTC cron windows; sync `main`; `git fetch --prune`.
