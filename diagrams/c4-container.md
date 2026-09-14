# C4 Level 2: Containers

The deployable and runnable pieces, where each one runs, and how they depend on each other.
"Container" is meant in the C4 sense (a separately running unit), not a Docker container.

```mermaid
flowchart TB
    visitor(["👤 Visitor"])

    subgraph vercel["Vercel"]
        web["<b>Web app</b><br/>Next.js 16 · React 19 · Tailwind v4<br/><small>/nfl · /cfb · /[sport]/matchup/[gameId] · /how-it-works<br/>server components, fetch revalidate 30s</small>"]
    end

    subgraph railway["Railway, production environment"]
        api["<b>API</b><br/>FastAPI + uvicorn<br/><small>/api/teams · /api/schedule · /api/games<br/>/api/predictions/{game_id} · /api/record<br/>runs alembic upgrade head on every boot</small>"]
        nflcron["<b>nfl-cron</b><br/><small>python -m data_pipeline.refresh_week<br/>0 9 * 9,10,11,12,1,2 * (UTC)</small>"]
        cfbcron["<b>cfb-cron</b><br/><small>python -m data_pipeline.refresh_week_cfb<br/>0 10 * 8,9,10,11,12,1 * (UTC)</small>"]
        db[("<b>Postgres 16</b><br/><small>schema managed by Alembic<br/>persistent volume</small>")]
    end

    artifacts[["<b>Model artifacts, committed to git</b><br/><small>backend/ml/artifacts/latest.json · cfb/latest.json<br/>model_1.0.0.joblib · cfb/model_cfb-1.0.0.joblib</small>"]]

    subgraph github["GitHub"]
        ci["<b>CI</b><br/><small>backend: ruff + pytest<br/>frontend: eslint + jest + next build</small>"]
    end

    external["External APIs<br/><small>nflverse · CFBD · The Odds API<br/>Visual Crossing · ESPN · Anthropic</small>"]

    visitor -->|HTTPS| web
    web -->|"JSON over HTTPS, server to server"| api
    api -->|"SQLAlchemy reads"| db
    nflcron -->|"upserts"| db
    cfbcron -->|"upserts"| db
    nflcron --> external
    cfbcron --> external
    nflcron -.->|"load_latest()"| artifacts
    cfbcron -.->|"load_latest()"| artifacts
    github -.->|"push to main deploys"| vercel
    github -.->|"push to main deploys"| railway
```

**One codebase, three Railway services.** The API and both cron jobs build from the same
`backend/` directory with the same pinned dependencies; they differ only in start command. The
API's comes from `railway.json`; each cron's comes from its own `railway-*-cron.json`, alongside
its schedule. Cron schedules are UTC and list months explicitly because standard cron has no
range that wraps from December into January.

**The API never loads the model.** From `ml/` it imports only `market_home_prob()` (to grade the
market side of the season record). Model artifacts are loaded by `predict_week`, which only the
cron jobs run. See [`prediction-request-sequence.md`](prediction-request-sequence.md).

**Why the model files are in git:** `ml/train.py` pins no random seed, so a retrain on a deploy
target wouldn't reproduce the weights behind the published accuracy numbers. See "Committing the
trained model artifacts, as an exception" in [`DECISIONS.md`](../DECISIONS.md).

**Deploys follow `main`; CI gates PRs.** Vercel and Railway each deploy on a push to `main`
through their own GitHub integrations. CI runs on every PR and on pushes to `main`, but it's a
merge gate, not a deploy trigger.

---
_Last updated: 2026-09-14 · reflects v1.0.10_
