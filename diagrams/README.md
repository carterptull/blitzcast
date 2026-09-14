# Architecture diagrams

Visual companions to [`CLAUDE.md`](../CLAUDE.md) (how the repo is laid out) and
[`DECISIONS.md`](../DECISIONS.md) (why it was built this way). The diagrams show the shape of
each decision; the decision log explains the reasoning behind it.

| Diagram | Shows |
| --- | --- |
| [`overview.md`](overview.md) | Start here: the request side and the batch side in one picture |
| [`c4-context.md`](c4-context.md) | Who and what Blitzcast talks to |
| [`c4-container.md`](c4-container.md) | The deployable pieces: web app, API, two cron services, Postgres, model artifacts, CI |
| [`er-diagram.md`](er-diagram.md) | The Postgres schema, and the invariants that live in it |
| [`prediction-request-sequence.md`](prediction-request-sequence.md) | What happens when someone opens a matchup page (no model runs) |
| [`daily-refresh-sequence.md`](daily-refresh-sequence.md) | What the Railway crons do every morning in season, step by step |
| [`llm-narration-boundary.md`](llm-narration-boundary.md) | Exactly where Claude sits, and the guardrails its output must pass |
| [`ml-pipeline.md`](ml-pipeline.md) | Training, walk-forward validation, and daily serving as three separate paths |
| [`game-lifecycle-state.md`](game-lifecycle-state.md) | A game from scheduled to graded, and which columns decide each state |
| [`deployment-security.md`](deployment-security.md) | Hosting, trust boundaries, and the security controls at each hop |

## Keeping these current

These are hand-maintained, not generated. Each file ends with a stamp
(`Last updated: <date> · reflects v<version>`, the version taken from `frontend/package.json`),
so a stale diagram is visible rather than silent.

Bump every diagram's footer to the current release version on each release, even ones whose
content didn't change this time; the stamp is a "still accurate as of this version" claim, not
a record of when the file itself was last edited. Content is a separate question from the
stamp: re-verify what a diagram actually shows only when a change touches one of the areas
below, and update its Mermaid source and prose then, not on every release.

| If you change... | Re-check |
| --- | --- |
| an Alembic migration or `backend/app/models.py` | `er-diagram.md` |
| `refresh_week*.py`, a pipeline step, or a `railway-*-cron.json` schedule | `daily-refresh-sequence.md`, `c4-container.md` |
| `backend/app/services/narrate.py` guardrails or prompt rules | `llm-narration-boundary.md` |
| `backend/app/services/predictions.py` or caching in `frontend/src/lib/api.ts` | `prediction-request-sequence.md` |
| `ml/train.py` windows, `ml/backtest.py`, or `ml/explain.py` | `ml-pipeline.md` |
| completion or grading rules | `game-lifecycle-state.md` |
| `next.config.ts` headers, CORS, hosting, or a new external API | `deployment-security.md`, `c4-context.md` |

A routine UI or copy change doesn't need a diagram update.

## Syntax rules (GitHub's Mermaid renderer)

- No native `C4Context` / `C4Container`: still experimental and inconsistent on GitHub. The C4
  views here are `flowchart`s styled by level.
- `flowchart` labels break lines with `<br/>`, never `\n`.
- `stateDiagram-v2` transition labels and `classDiagram` relationship labels are single-line
  plain text: no `\n`, no colons.
- Verify by viewing the rendered file on github.com. Reading the source is not verification.

---
_Last updated: 2026-09-14 · reflects v1.0.11_
