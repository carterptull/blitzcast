# The LLM narration boundary

Claude writes the broadcaster-style explanation on every matchup page. It never produces or
changes a number. This diagram shows where that line sits and the checks
`backend/app/services/narrate.py` runs before any generated text is stored.

```mermaid
flowchart TB
    subgraph fixed["Decided before Claude is called: deterministic and tested"]
        prob["Calibrated home win probability<br/><small>XGBoost + Platt calibration</small>"]
        factors["Top 4 SHAP factors<br/><small>ml/explain.py top_factors()<br/>market factors take direction from the raw value, not the SHAP sign</small>"]
        extras["Context notes<br/><small>Vegas spread · CFB: poll standing, conference matchup</small>"]
    end

    payload["build_narration_payload()<br/><small>app/jobs/predict_week.py</small>"]
    key{"ANTHROPIC_API_KEY set?"}
    prompt["System prompt<br/><small>broadcaster voice · never state another probability<br/>never invent a stat · 2 to 4 sentences · no betting advice<br/>CFB adds: never cite injuries</small>"]

    subgraph llm["The only non-deterministic step"]
        claude["Claude Haiku 4.5<br/><small>messages.create, max_tokens 300</small>"]
    end

    clean["_call_api() then _plain_punctuation()<br/><small>surrounding markdown symbols stripped<br/>em and en dashes become commas, spacing tidied</small>"]
    g1{"_percentages_consistent<br/><small>every percentage within 1 point of<br/>the home or away probability?</small>"}
    g2{"_favorite_attribution_consistent<br/><small>favorite, favored, or the edge attached<br/>to the team the model actually favors?</small>"}
    g3{"_market_attribution_consistent<br/><small>in sentences about Vegas, the line, or the spread,<br/>favorite matches the raw spread's sign?</small>"}
    retry{"First attempt?"}
    wait["Wait 2s, try once more"]
    accept(["✅ Store the narrative"])
    none(["⛔ Store NULL<br/><small>page shows the factor list without prose</small>"])
    row[("predictions row<br/><small>probability and factors are written<br/>unchanged either way</small>")]

    prob --> payload
    factors --> payload
    extras --> payload
    payload --> key
    key -->|no| none
    key -->|yes| prompt --> claude --> clean --> g1
    g1 -->|yes| g2
    g2 -->|yes| g3
    g3 -->|yes| accept
    g1 -->|no| retry
    g2 -->|no| retry
    g3 -->|no| retry
    claude -.->|"API error"| retry
    retry -->|yes| wait --> claude
    retry -->|no| none
    accept --> row
    none --> row

    style fixed fill:transparent,stroke:#2E7D32,stroke-width:2px
    style llm fill:transparent,stroke:#C62828,stroke-width:2px,stroke-dasharray: 5 5
```

**Why the line is here:** keeping the prediction deterministic and testable is the whole point of
using a real, backtested model. If a language model could touch the number, the walk-forward
results would describe something other than what visitors see. See "LLM narration layer strictly
downstream of the model, never upstream" in [`DECISIONS.md`](../DECISIONS.md).

**A failed narration costs prose, never a prediction.** At most two API calls per game; any
failure, including a missing key, stores `NULL` and the page falls back to the factor list. The
probability and factors in the same row are written identically either way.

**Each guardrail exists because of a real production bug.** The percentage check alone passed
narrations that cited the right number while calling the underdog "a slight favorite", so the
favorite-attribution check was added. Then a narration correctly named the model's favorite while
misstating which team *Vegas* favored, which the market check now catches. Market factors' SHAP
direction is also grounded in raw data upstream, for the same reason. See the three narration and
SHAP-direction entries in [`DECISIONS.md`](../DECISIONS.md).

**Known gap (CFB only):** team matching uses every word of a team's stored name plus its
abbreviation. NFL names include the nickname ("Buffalo Bills"), but CFB names are school names,
so a CFB sentence that names a team only by mascot ("the Bruins") isn't checked.

---
_Last updated: 2026-09-14 · reflects v1.0.11_
