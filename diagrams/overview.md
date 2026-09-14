# Overview: the whole system in one diagram

Start here. Blitzcast is two halves that only meet in the database: a request side that serves
pages, and a batch side that does all the actual work once a day. Every box below is expanded
in its own diagram (see the table at the bottom).

```mermaid
flowchart TB
    visitor(["👤 Visitor<br/><small>blitzcast.app, or the portfolio embed</small>"])

    subgraph request["Request side: every page view"]
        direction LR
        web["🖥️ Next.js on Vercel<br/><small>server components<br/>30s fetch revalidation</small>"]
        api["⚙️ FastAPI on Railway<br/><small>read-only JSON API</small>"]
    end

    db[("🗄️ Postgres 16<br/><small>games · odds · weather · injuries<br/>polls · predictions</small>")]

    subgraph batch["Batch side: once a day, in season"]
        direction LR
        cron["⏰ Railway crons<br/><small>nfl-cron 09:00 UTC<br/>cfb-cron 10:00 UTC</small>"]
        sources["🌐 Sports data APIs<br/><small>nflverse · CFBD · The Odds API<br/>Visual Crossing · ESPN</small>"]
        predict["📈 predict_week<br/><small>XGBoost + Platt calibration<br/>SHAP top factors</small>"]
        claude["💬 Claude Haiku 4.5<br/><small>narration only</small>"]
    end

    visitor -->|HTTPS| web
    web -->|"GET /api/*"| api
    api -->|"SELECT cached rows"| db

    cron -->|fetch| sources
    cron -->|"idempotent upserts"| db
    cron --> predict
    predict -->|"probability + factors, fixed"| claude
    claude -.->|"prose, or nothing"| predict
    predict -->|"upsert predictions"| db

    style request fill:transparent,stroke:#1565C0,stroke-width:2px
    style batch fill:transparent,stroke:#2E7D32,stroke-width:2px
```

**The one thing to take away:** a page view never runs the model, never calls Claude, and never
touches a rate-limited API. It reads rows the batch side already wrote. That single decision is
why site traffic can't burn through The Odds API's 500 requests a month, and why a slow or failed
Claude call can't slow a page down (see "Batch-generated predictions, not per-request inference"
in [`DECISIONS.md`](../DECISIONS.md)).

**The model and the LLM are deliberately in a line, not side by side.** The model decides the
probability; Claude only receives it, already fixed, and turns it into prose. The dotted arrow
back is the whole of Claude's influence: text, or nothing at all.

## Go deeper

| Question | Diagram |
| --- | --- |
| Who uses the system, and what does it depend on? | [`c4-context.md`](c4-context.md) |
| What are the deployable pieces? | [`c4-container.md`](c4-container.md) |
| What does the database look like? | [`er-diagram.md`](er-diagram.md) |
| What happens when a matchup page loads? | [`prediction-request-sequence.md`](prediction-request-sequence.md) |
| What do the daily cron jobs do? | [`daily-refresh-sequence.md`](daily-refresh-sequence.md) |
| How is Claude kept from touching the numbers? | [`llm-narration-boundary.md`](llm-narration-boundary.md) |
| How is the model trained, validated, and served? | [`ml-pipeline.md`](ml-pipeline.md) |
| How does a game go from scheduled to "Called it"? | [`game-lifecycle-state.md`](game-lifecycle-state.md) |
| How is it hosted and secured? | [`deployment-security.md`](deployment-security.md) |

---
_Last updated: 2026-09-14 · reflects v1.0.10_
