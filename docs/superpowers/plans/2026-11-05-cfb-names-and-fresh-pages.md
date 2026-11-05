# CFB team-name matching and fresh pages (v1.2.6)

**Goal:** a patch release that (1) lets CFB odds match schools whose CFBD name carries an accent
or apostrophe (San José State, Hawai'i), and (2) stops a rarely visited page from showing a
days-old prediction to its first visitor.

**Spec:** this file (no separate spec). Evidence, 2026-11-05 production:
- CFB cron log: `skipping event, unknown team: "unrecognized CFB team name: 'San Jose State Spartans'"`
  and the same for `'Hawaii Rainbow Warriors'`. NIU @ SJSU and HAW @ UTEP show Spread/Moneyline/Total N/A.
- Matchup pages for upcoming games showed `predicted Nov 2` / `Nov 3` / `Nov 4` on first load after a
  successful Nov 5 cron run, and `Nov 5` on reload. The database was correct; Vercel served the last
  rendered copy (stale-while-revalidate) once.

## Global Constraints

- Python: ruff-clean, minimal comments, pinned deps unchanged. Tests: `python -m pytest` from `backend/`
  using `.venv\Scripts\python`. Lint: `python -m ruff check .`
- Frontend: `npm run lint`, `npm test`, `npm run build` from `frontend/` must pass.
- `backend/data_pipeline/seeds/cfb_team_aliases.json` is generated, never hand-edited.
- No user-visible em or en dashes (literal or `&mdash;`/`&ndash;`).
- No AI attribution anywhere in commits, PRs, code or docs. Commits are authored by the repo's
  configured git user; never pass `--author`, never add `Co-Authored-By` or session trailers.
- Never print secret values (API keys) to output or files.
- Do not change the model, `MODEL_VERSION`, or the narration guardrails.

## Task 1: Fold accents and apostrophes in the CFB name normalizer

**Files:** `backend/data_pipeline/cfb_team_names.py`, `backend/tests/test_cfb_pipeline.py`,
`backend/data_pipeline/seeds/cfb_team_aliases.json` (regenerated).

**Root cause:** `normalize()` is `re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()`. It deletes `é`
(so CFBD's "San José State" keys as `san jos state`) and turns an apostrophe into a space
(CFBD's "Hawai'i" keys as `hawai i`). The Odds API sends "San Jose State Spartans" and
"Hawaii Rainbow Warriors", which key as `san jose state spartans` / `hawaii rainbow warriors`, so
no alias matches and the prefix fallback cannot help.

**Change `normalize()`** so that, before the existing regex:
1. Unicode NFKD decomposition, then drop combining marks (`unicodedata.combining`), so `é` becomes `e`.
2. Delete apostrophe-like characters outright (no space): ASCII `'`, U+2019 `’`, U+2018 `‘`,
   U+02BB `ʻ` (okina), U+02BC `ʼ`, and backtick.
Then lowercase and apply the existing `[^a-z0-9]+` to space collapse and strip. Keep it a small,
plain function.

**Tests (write first, see them fail, then implement)** in `backend/tests/test_cfb_pipeline.py`,
following the file's existing fixture style (`TEAMS_DF` / `build_alias_map`). Add fixture rows for
`San José State` (mascot `Spartans`, abbreviation `SJSU`) and `Hawai'i` (mascot `Rainbow Warriors`,
abbreviation `HAW`) if the fixture lacks them; if adding rows to the shared fixture would disturb
existing tests, build a local DataFrame in the new tests instead. Assert:
- `normalize("San José State") == "san jose state"`, `normalize("Hawai'i") == "hawaii"`,
  `normalize("Hawaiʻi") == "hawaii"`, `normalize("Hawai’i") == "hawaii"`,
  `normalize("Miami (OH)") == "miami oh"` (unchanged behavior), `normalize("Texas A&M") == "texas a m"`.
- `cfb_to_abbr` resolves `San Jose State Spartans`, `San José State Spartans`, `San Jose State`
  to `SJSU` and `Hawaii Rainbow Warriors`, `Hawai'i Rainbow Warriors`, `Hawaii` to `HAW`.

**Regenerate the alias file without touching any database.** `seed_cfb.main()` writes to Postgres,
and Docker is not running, so do NOT run `python -m data_pipeline.seed_cfb`. Instead write a
throwaway script OUTSIDE the repo (in the scratchpad dir given in your dispatch) that reproduces
exactly the alias half of `seed_cfb.main()` with its defaults (`--start 2021 --end 2026`):
`fbs = cfbd.load_fbs_teams(2026).sort_values("school")`, `fcs = cfbd.load_fcs_teams(2026).sort_values("school")`,
`wanted = seed_cfb.fcs_schools_on_fbs_schedules(list(range(2021, 2027)))`, `fcs = fcs[fcs["school"].isin(wanted)]`,
`teams = pd.concat([fbs, fcs], ignore_index=True)`, `aliases = build_alias_map(teams)`, `save_aliases(aliases)`.
Run it with `backend/` as the working directory so `app.config` finds `backend/.env` (CFBD_API_KEY is
set there; never print it). This costs about 9 CFBD requests.

**Verify the regenerated file** with a second throwaway script comparing `git show HEAD:<path>` to
the new file, and put the numbers in your report:
- the set of abbreviation VALUES is identical (no team gained, lost or renamed an abbr);
- list every removed key and every added key; every removed key must be an old accent/apostrophe
  form whose replacement key is present (e.g. `san jos state` to `san jose state`, `hawai i` to `hawaii`);
- every key present in both maps the same abbr;
- note any `dropped ambiguous alias` lines printed during the build, old vs new.
If any check fails, stop and report BLOCKED with the evidence instead of committing.

**Done when:** new tests pass, full `python -m pytest` passes, `python -m ruff check .` is clean,
the diff check above passes. Commit: `fix(cfb): match accented and apostrophe school names in odds`.

## Task 2: Bounded freshness for matchup and slate pages

**Maintainer's choice (2026-11-05):** bounded cache. Keep the 30-second cache that makes repeat
week-selector clicks fast (DECISIONS.md, "Short revalidation window over `no-store`"), but make it
impossible for a visitor to see data older than about 5 minutes.

**Files:** `frontend/src/lib/api.ts`, `frontend/src/app/[sport]/matchup/[gameId]/page.tsx`,
`frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx`, tests under
`frontend/src/lib/__tests__/` (and a jest mock for `next/cache` if needed).

**Why stale happens today:** `get()` uses `fetch(..., { next: { revalidate: 30 } })` and the matchup
page exports `revalidate = 30`. Both are stale-while-revalidate: the first request after expiry is
served the old entry (however old) and a refresh runs in the background. A page nobody opened for
three days shows three-day-old data once.

**Design:**
1. In `api.ts`, the live (non-mock) path of `get()` reads through
   `unstable_cache` from `next/cache` (already used by `frontend/src/app/sitemap.ts`) with
   `revalidate: 30` and key parts `["api", path, String(window)]`, where
   `window = Math.floor(Date.now() / FRESH_WINDOW_MS)` and `FRESH_WINDOW_MS = 5 * 60 * 1000`
   (a named module constant). The inner fetch uses `cache: "no-store"` because `unstable_cache`
   now owns caching. A new window is a new key, so it is a cache miss and a blocking fresh fetch:
   worst-case age is the window length. Within a window, the 30-second revalidation still serves
   repeat clicks from cache.
2. Error behavior is unchanged: network failure gives `ApiUnreachableError`, 404 gives
   `NotFoundError`, other non-OK gives `ApiUnreachableError` with the status. Errors must not be
   cached (a thrown error inside `unstable_cache` is not stored; confirm).
3. Matchup page: replace `export const revalidate = 30;` with `export const dynamic = "force-dynamic";`
   so the page renders per request from the bounded data cache instead of being a full-route ISR
   copy. The slate page already renders per request (it reads `searchParams`).
4. Matchup OG image: replace `export const revalidate = 300;` with
   `export const dynamic = "force-dynamic";` for the same reason (a share card should not show a
   days-old probability).
5. Update the comment above the cache call to say what it does now, briefly.
6. Before writing code, confirm in the installed Next.js 16 (read `frontend/node_modules/next`
   docs or types, e.g. `node_modules/next/dist/docs` if present, and `next/cache` exports) that
   `unstable_cache` and `export const dynamic = "force-dynamic"` are supported in this version
   without `cacheComponents`, and that nesting (sitemap's `unstable_cache` around `getSchedule`) is
   allowed. If any of that is not true, stop and report NEEDS_CONTEXT with what you found.

**Tests (TDD):** in `frontend/src/lib/__tests__/api.test.ts` (or a new file beside it), with
`next/cache` mocked so `unstable_cache` is observable: the live path calls `unstable_cache` with key
parts containing the path and the current window number and `{ revalidate: 30 }`; the inner fetch
uses `cache: "no-store"`; two `Date.now()` values in different 5-minute windows give different key
parts; 404 maps to `NotFoundError`; a fetch rejection maps to `ApiUnreachableError`. Keep the
existing tests passing.

**Real-runtime check (required):** write a tiny stub API server in the scratchpad dir (Node `http`,
any free port) that serves JSON for the paths the matchup page calls and counts hits and returns a
value you can change. Build and start production (`npm run build` then `npm run start` on a free
port) with `NEXT_PUBLIC_API_BASE_URL` pointed at the stub and `NEXT_PUBLIC_USE_MOCK` unset. Show
that: (a) two requests to the same matchup page within 30 seconds cause at most one stub hit;
(b) after changing the stub's value and waiting past the next 5-minute window boundary, the very
first request shows the new value (not the old one). Put the hit counts and timings in your report.
Use `npm run build` (not dev) because dev mode does not cache. Stop every server you start.

**Done when:** `npm run lint`, `npm test`, `npm run build` pass; the runtime check passes.
Commit: `fix(frontend): bound how stale a cached page can be`.

## Task 3: Release 1.2.6 paperwork

**Files:** `frontend/package.json` and `frontend/package-lock.json` (both top-level `version`
fields, 1.2.5 to 1.2.6; edit the lockfile's two root `version` entries by hand or with
`npm version 1.2.6 --no-git-tag-version` from `frontend/`, nothing else in the lockfile may change),
`CHANGELOG.md`, `DECISIONS.md`, every file in `diagrams/`.

1. **CHANGELOG:** new `## [1.2.6] — 2026-11-05` section under `## [Unreleased]`, matching the
   existing heading format. One opening line: a patch release, no change to the model or
   `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`). `### Fixed`: (a) CFB odds now match schools whose name
   carries an accent or apostrophe; San José State and Hawai'i games had no spread, moneyline or
   total because the Odds API spells them "San Jose State" and "Hawaii"; the alias file was
   regenerated. (b) A page nobody had opened for a while could show its first visitor a prediction
   that was days old (the database was current; the cached page was not); cached reads now expire
   within about 5 minutes while repeat clicks stay cached for 30 seconds; matchup pages and share
   images render per request. Plain language, same tone as earlier entries.
2. **DECISIONS:** (a) append a dated paragraph to the end of the existing section
   "Short revalidation window over `no-store` for slate/matchup fetches" explaining the 2026-11-05
   change: stale-while-revalidate meant the window bounded refresh frequency, not age; the fix keys
   `unstable_cache` to a 5-minute window so the worst case is about 5 minutes; alternatives
   considered and rejected: `no-store` (brings back the mobile stall this section exists to avoid),
   cron-triggered on-demand revalidation (a shared secret and a new public route for little gain).
   (b) a new short section near the CFB name-resolution material (search for `cfb_team_aliases` or
   "alias") titled like "Folding accents and apostrophes in CFB name matching": the bug, why it was
   fixed in `normalize()` rather than by hand-adding aliases (the alias file is generated), and that
   the regenerated file kept every team's abbreviation (use the counts from Task 1's report given
   in your dispatch).
3. **Diagrams:** update content where it describes the old cache: `diagrams/c4-container.md`
   ("fetch revalidate 30s"), `diagrams/overview.md` ("30s fetch revalidation"),
   `diagrams/prediction-request-sequence.md` (the `revalidate 30` fetch and "refetched in the
   background once older than 30s" lines, plus its prose if it describes caching). Describe it as:
   30 s cache, at most about 5 minutes old. Keep GitHub Mermaid rules in `diagrams/README.md`
   (`<br/>` not `\n`, no colons in state/class labels). Then set every diagram footer (including
   `diagrams/README.md`) to `_Last updated: 2026-11-05 · reflects v1.2.6_`.
4. Grep the repo (excluding node_modules, .venv, .git, CHANGELOG history) for other mentions of the
   30-second revalidation or `revalidate = 30` in docs (README.md, backend/README.md, CLAUDE.md)
   and update any that are now wrong.
5. No em or en dashes in anything a visitor sees (these files are docs, but do not add dashes to UI).

**Done when:** `npm test` and `npm run lint` still pass (version change only). Commit:
`chore(release): 1.2.6 changelog, decisions, diagrams`.
