# ER diagram: the Postgres schema

All ten tables from `backend/app/models.py` (managed by the three Alembic migrations in
`backend/alembic/versions/`). NFL and CFB share every table, separated by a `sport` column
rather than a second schema.

```mermaid
erDiagram
    stadiums |o--o{ teams : "home stadium"
    stadiums |o--o{ games : "venue"
    teams ||--o{ games : "home team"
    teams ||--o{ games : "away team"
    games ||--o{ team_game_stats : "box score"
    teams ||--o{ team_game_stats : "per team"
    teams ||--o{ team_ratings : "Elo snapshots"
    games ||--o{ odds : "one row per source"
    games ||--o| weather : "kickoff forecast"
    games ||--o{ injuries : "listed for game"
    teams ||--o{ injuries : "player on team"
    teams ||--o{ poll_ranks : "ranked"
    games ||--o{ predictions : "one per model_version"

    stadiums {
        int stadium_id PK
        string name
        string city
        float lat
        float lon
        bool is_dome
        string surface
    }
    teams {
        int team_id PK
        string sport UK "NFL or CFB, unique with abbr"
        string abbr UK
        string name
        string conference
        string division "NFL only"
        string tier "CFB only, FBS or FCS"
        int espn_id
        string color
        string alt_color
        string logo_url
        int stadium_id FK
    }
    games {
        string game_id PK "nflverse id, or cfb_ prefix"
        string sport
        int season
        int week
        date game_date
        timestamptz kickoff_time "NULL means TBD"
        int home_team_id FK
        int away_team_id FK
        int stadium_id FK "NULL for neutral-site NFL games"
        string venue_name "raw venue when there is no stadium row"
        bool is_neutral_site
        bool is_primetime
        bool is_divisional
        int home_score "completion source of truth"
        int away_score "completion source of truth"
        string status "derived, never key completion on it"
        float spread_line "closing line, training feature"
        float total_line
        int home_moneyline
        int away_moneyline
    }
    team_game_stats {
        string game_id PK, FK
        int team_id PK, FK
        int points
        float yards
        float epa_offense
        float epa_defense
        int turnovers
    }
    team_ratings {
        string sport PK
        int team_id PK, FK
        int season PK
        int week PK
        float elo_rating "inspection only"
    }
    odds {
        int odds_id PK
        string game_id FK, UK "unique with source"
        string source UK
        float spread_home
        int moneyline_home
        int moneyline_away
        float total
        timestamptz captured_at "refreshed on every upsert"
    }
    weather {
        string game_id PK, FK
        float temp_f
        float wind_mph
        bool precipitation
        string conditions
        timestamptz captured_at
    }
    injuries {
        int injury_id PK
        string game_id FK, UK "unique with team and player"
        int team_id FK, UK
        string player_name UK
        string position
        string status
        date report_date
    }
    poll_ranks {
        int poll_rank_id PK
        string sport UK "unique with season, week, poll, team"
        int season UK
        int week UK "ranking entering this week"
        string poll UK
        int team_id FK, UK
        int rank
    }
    predictions {
        int prediction_id PK
        string game_id FK, UK "unique with model_version"
        string model_version UK "1.0.0, cfb-1.0.0, or backtest-*"
        float home_win_prob "calibrated"
        timestamptz predicted_at
        jsonb shap_top_features "top 4 factors"
        text llm_narrative "NULL when narration failed"
    }
```

**Completion lives in two nullable columns, not in `status`.** A game is over when
`home_score` and `away_score` are both present, checked directly at every call site: the
`?status=` filter, the verdict badge, the season record. `status` is derived and unindexed, and
the NFL loader still sets it from the home score alone. See "Completion keyed on scores,
never on `Game.status`" in [`DECISIONS.md`](../DECISIONS.md).

**`predictions` is unique on `(game_id, model_version)`, and that constraint does real work.**
Live rows carry `1.0.0` / `cfb-1.0.0`; walk-forward reconstructions of 2023-2025 carry
`backtest-1.0.0` / `backtest-cfb-1.0.0`. The slate's probability and `/api/record` both filter
`model_version NOT LIKE 'backtest%'`, so reconstructed history can never pose as a live call.
The matchup page is the one reader that takes the newest row of any version, and it labels a
reconstructed row as such. Re-running `predict_week` updates the same row rather than adding one.

**`odds` is a snapshot, not a history.** There is one row per `(game_id, source)`, overwritten
by each daily refresh with a fresh `captured_at`. Readers take the newest row; when a game has
none (every historical game), the matchup page falls back to the closing lines stored on `games`.

**`team_ratings` isn't on any serving path.** `ml.compute_ratings` writes Elo snapshots for
inspection; `ml/features.py` replays Elo from game results itself whenever it builds features.
CFB has no rows in `injuries` (there is no standardized CFB injury report), and NFL has none in
`poll_ranks`.

---
_Last updated: 2026-09-14 · reflects v1.0.11_
