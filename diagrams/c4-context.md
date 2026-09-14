# C4 Level 1: System context

Blitzcast as a single box: the people and systems around it, and which direction data flows.

```mermaid
flowchart LR
    visitor(["👤 Visitor<br/><small>fan checking a matchup</small>"])
    portfolio(["🖼️ Portfolio site<br/><small>embeds Blitzcast in an iframe</small>"])

    blitz["<b>Blitzcast</b><br/><small>NFL and college football win probabilities<br/>with plain-language explanations</small>"]

    subgraph data["Sports data, pulled by daily batch jobs"]
        nflverse["nflverse<br/><small>schedules, scores, play-by-play EPA,<br/>historical lines, injury fallback</small>"]
        cfbd["CollegeFootballData<br/><small>CFB teams, venues, games,<br/>lines, PPA, polls, logos</small>"]
        odds["The Odds API<br/><small>current NFL and CFB odds<br/>free tier, 500 requests a month</small>"]
        vc["Visual Crossing<br/><small>kickoff weather forecasts</small>"]
        espn["ESPN<br/><small>NFL injury report, NFL logos</small>"]
    end

    anthropic["Anthropic API<br/><small>Claude Haiku 4.5, narration only</small>"]

    subgraph hosting["Hosting"]
        cloudflare["Cloudflare<br/><small>blitzcast.app domain and DNS</small>"]
        vercel["Vercel<br/><small>frontend</small>"]
        railway["Railway<br/><small>API, cron jobs, Postgres</small>"]
    end

    visitor -->|HTTPS| blitz
    portfolio -.->|"iframe, allowed by CSP frame-ancestors"| blitz
    blitz -->|"daily batch pulls"| data
    blitz -->|"narrate finished predictions"| anthropic
    blitz -.->|"runs on"| hosting
```

**Only two things reach Blitzcast in real time:** visitors, and the portfolio site that frames
it. Every data provider sits on the batch side and is called by scheduled jobs, so each free
tier's budget is set by the cron schedule, not by how many people visit.

**Anthropic is a dependency, not an authority.** It receives a finished probability and its top
factors and returns prose. It has no way to change a number, and if it's down (or its output
fails a guardrail) predictions still ship, just without narration. See
[`llm-narration-boundary.md`](llm-narration-boundary.md).

**ESPN shows up for two unrelated reasons:** the NFL injury refresh reads ESPN's unofficial
injuries endpoint (falling back to nflverse if it fails), and NFL team logos come from ESPN's
CDN. CFB logos come from CollegeFootballData instead.

---
_Last updated: 2026-09-14 · reflects v1.0.10_
