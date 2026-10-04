# State diagram: a game's lifecycle

What a single game goes through, from appearing on the schedule to being graded on the
season record, and which data decides each transition.

```mermaid
stateDiagram-v2
    state "Called it" as CalledIt
    state "Missed" as Missed
    state "Ungraded" as Ungraded

    [*] --> Scheduled: schedule sync inserts the game
    Scheduled --> Predicted: predict_week writes a live prediction row up to 7 days before kickoff
    Predicted --> Predicted: next daily run re-predicts while both scores are NULL
    Predicted --> Final: schedule sync writes both scores
    Scheduled --> Final: finished without a live prediction
    Final --> CalledIt: model pick matched the winner
    Final --> Missed: model pick did not match
    Final --> Ungraded: tie, exact 0.5 pick, or no prediction
    CalledIt --> [*]
    Missed --> [*]
    Ungraded --> [*]

    note right of Final
        Final means home_score AND away_score are both present.
        The status column is never consulted.
    end note
```

**The both-scores rule holds at every call site:** both schedule loaders' status, `refresh_stats`,
the feature builder's played-game checks (`_team_form`, `home_win`), the prediction status filter,
verdict grading, and the season record.

**Grading is one function, `prediction_verdict()`** in `backend/app/services/predictions.py`. It
returns nothing to grade when there's no prediction, either score is missing, the game tied, or
the probability is exactly 0.5; otherwise it compares the side the model favored with the side
that won. Newly written predictions are never exactly 0.5, because `predict_week` nudges an
exact tie 0.0001 toward the betting favorite, so the exact 0.5 rule only matters for finished
games stored before v1.1.2. The same function drives the "Called it" / "Missed" badge on the slate and matchup page.

**The season record is stricter than the badge.** `/api/record` only counts a game when the
*market* can be graded the same way (a market probability exists, de-vigged from moneylines or
derived from the spread when they're missing, and isn't exactly 0.5), and it ignores `backtest-*` rows entirely, so the model and the market are always compared
on an identical set of games. See "Record always paired with the market baseline" in
[`DECISIONS.md`](../DECISIONS.md).

**Which games get predicted:** `default_week()` picks the earliest week that still has a game
with no scores, but treats a week as done 36 hours after the latest kickoff among its
still-unscored games, so a cancelled game can't pin the daily job to an old week forever.
Since v1.1.2 the daily job also predicts any unplayed game kicking off within 7 days
(`LOOKAHEAD_DAYS`), so a game can move from Scheduled to Predicted before its week becomes the
default week. Grading is unchanged: it starts only once both scores exist.

**Kickoff-gated, not just score-gated.** "Unplayed" isn't only "both scores are NULL":
`unplayed_game_ids()` also excludes a game once its kickoff has passed, even with no score yet.
Without that, a game already underway (or one whose final score simply hasn't landed from the
data source yet) would get silently re-predicted on the next cron, with a `predicted_at` that
lies about when the call was actually made, even though the inputs are unchanged (there's no
live/in-progress data to leak in). A NULL kickoff is a still-TBD future game and stays eligible
regardless of `now`, matching how `default_week` already treats it. In the look-ahead selection
a TBD kickoff is judged by its game date.

---
_Last updated: 2026-10-03 · reflects v1.1.2_
