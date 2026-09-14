# Sequence diagram: the daily refresh

What each Railway cron service runs every morning in season: pull fresh data, then generate and
narrate predictions for the current week. NFL and CFB run the same shape with different steps.

```mermaid
sequenceDiagram
    autonumber
    participant R as Railway cron
    participant O as refresh_week orchestrator
    participant P as Pipeline step subprocess
    participant X as External APIs
    participant DB as Postgres
    participant J as predict_week
    participant L as narrate.py and Claude

    alt NFL, nfl-cron at 09:00 UTC
        R->>O: python -m data_pipeline.refresh_week
        O->>P: refresh_schedule
        P->>X: nflverse schedules
        P->>DB: upsert games, including final scores
        O->>P: refresh_stats
        P->>X: nflverse play-by-play
        P->>DB: upsert team_game_stats
        O->>P: refresh_odds
        P->>X: The Odds API, one call for every game
        P->>DB: upsert odds for games kicking off in the next 14 days
        O->>P: refresh_weather
        P->>X: Visual Crossing by lat/lon, or by venue name for neutral sites
        P->>DB: upsert weather, domes skipped
        O->>P: refresh_injuries
        P->>X: ESPN injuries, nflverse as fallback
        P->>DB: upsert injuries onto each team's next game
    else CFB, cfb-cron at 10:00 UTC
        R->>O: python -m data_pipeline.refresh_week_cfb
        O->>P: refresh_schedule_cfb
        P->>X: CollegeFootballData games
        P->>DB: upsert games, including final scores
        O->>P: refresh_odds --sport cfb
        P->>DB: upsert odds
        O->>P: refresh_weather --sport cfb
        P->>DB: upsert weather
        O->>P: refresh_polls_cfb
        P->>X: CollegeFootballData AP and Coaches polls
        P->>DB: upsert poll_ranks
    end
    Note over O,P: Every step is its own subprocess. A failed step is logged and the next one still runs.
    alt schedule sync failed
        O-->>R: skip the prediction batch
    else schedule sync succeeded
        O->>J: python -m app.jobs.predict_week, plus --sport cfb for CFB
        J->>DB: default_week() finds the earliest week with an unplayed game
        J->>DB: build_features() for the season, each row as of its kickoff
        loop each game that week with both scores NULL
            J->>J: predict_proba, Platt calibration, top_factors via SHAP
            J->>L: narrate(probability, factors, spread, notes)
            L-->>J: guardrail-checked prose, or None
            J->>DB: upsert prediction on (game_id, model_version) and commit
        end
    end
```

**Soft-fail by design.** The orchestrator runs each step with `subprocess.run(..., check=False)`
and keeps going when one fails: stale weather is better than no predictions. The one hard
dependency is the schedule sync, because predicting against an out-of-date schedule could target
the wrong week or re-predict a game that has already finished.

**Idempotent and resumable.** Every loader upserts on a natural key, and `predict_week` commits
after each game, so a crash halfway through a ~100-game CFB slate keeps what finished and a
re-run simply overwrites the same rows.

**Free-tier budgets are set here, not by traffic.** The Odds API is called once per sport per day
(about 60 calls a month when both seasons overlap). Each call requests three markets, and The
Odds API bills markets × regions, so that is roughly 180 of the 500 monthly credits;
`refresh_odds` logs the remaining quota after every run. Visual Crossing stays under 1,000
records a day even with CFB's 8-day window. See "Odds API: one batch call per day, never per request" in
[`DECISIONS.md`](../DECISIONS.md).

**Schedules are UTC and season-scoped:** `0 9 * 9,10,11,12,1,2 *` (NFL) and
`0 10 * 8,9,10,11,12,1 *` (CFB), with months listed because cron can't express a range that wraps
into January. Outside those months the jobs simply don't fire.

---
_Last updated: 2026-09-14 · reflects v1.0.11_
