# Sequence diagram: loading a matchup page

What happens between a visitor opening `/nfl/matchup/2026_01_CHI_CAR` and the page rendering.
The important part is what's missing: no model, no Claude call, no external API.

```mermaid
sequenceDiagram
    autonumber
    actor V as Visitor
    participant N as Next.js server (matchup page)
    participant C as Next data cache
    participant A as FastAPI predictions router
    participant S as Prediction service
    participant DB as Postgres

    V->>N: GET /nfl/matchup/2026_01_CHI_CAR
    Note over N: generateMetadata and the page both call getMatchup(),<br/>deduplicated into a single fetch per render
    N->>C: fetch /api/predictions/2026_01_CHI_CAR with revalidate 30
    alt cached entry exists
        C-->>N: cached JSON, refetched in the background once older than 30s
    else no cached entry
        C->>A: GET /api/predictions/{game_id}
        alt BLITZCAST_MOCK=1
            A-->>C: fixture from mock_data.py
        else unknown game_id
            A->>S: get_prediction_detail(db, game_id)
            S->>DB: SELECT game with teams and stadium
            DB-->>S: no row
            S-->>A: None
            A-->>C: 404 game not found
        else game exists
            A->>S: get_prediction_detail(db, game_id)
            S->>DB: SELECT game with teams and stadium
            S->>DB: newest prediction for the game, by predicted_at
            S->>DB: weather, newest odds, poll ranks entering the week
            DB-->>S: rows
            S-->>A: PredictionOut
            A-->>C: 200 JSON
        end
        C-->>N: response
    end
    alt 404
        N-->>V: notFound() page
    else 200
        N-->>V: HTML with probability, SHAP factors, narration, score and verdict
    end
```

**Nothing is computed per request.** The probability, factors, and narration were written by the
daily batch (see [`daily-refresh-sequence.md`](daily-refresh-sequence.md)); this path is reads
only. See "Batch-generated predictions, not per-request inference" in
[`DECISIONS.md`](../DECISIONS.md).

**A game with no prediction yet still renders.** The service returns
`prediction_status: "pending"` with an empty factor list, so a newly scheduled game gets a real
page instead of an error.

**Why a 30-second cache and not `no-store`:** predictions change once a day, so a live
Vercel-to-Railway-to-Postgres round trip on every click bought no freshness and cost noticeable
latency on mobile. See "Short revalidation window over `no-store`" in
[`DECISIONS.md`](../DECISIONS.md).

**Two details worth knowing:** this read takes the newest prediction of *any* `model_version`
(the slate and `/api/record` exclude `backtest-*` rows; the matchup page instead shows a
reconstructed row with a label). And if Railway is unreachable, `api.ts` throws
`ApiUnreachableError`, which the page catches to render its `BackendDown` state (metadata falls
back to a plain "Matchup" title); `src/app/error.tsx` only handles other, unexpected errors.

---
_Last updated: 2026-09-14 · reflects v1.0.10_
