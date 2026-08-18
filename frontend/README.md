# Blitzcast Frontend

Next.js app for Blitzcast: the week slate and matchup pages that render
win probabilities and their explanations. It reads the FastAPI backend
over HTTP and owns no model logic of its own.

## Stack

- Next.js 16 (App Router, `src/`)
- React 19
- TypeScript 5
- Tailwind CSS v4
- Jest + Testing Library for unit tests
- Fonts: Anton, Newsreader, and IBM Plex Mono via `next/font/google`

## Routes

| Route | Purpose |
|---|---|
| `/` | Redirects to `/nfl` |
| `/[sport]` | Week slate for `nfl` or `cfb`, with a season record banner, status filter, and disagreements panel |
| `/[sport]/matchup/[gameId]` | Matchup detail: probability, factors, narration, final score and verdict once played |
| `/how-it-works` | Methodology page: model inputs, the leakage rule, the LLM boundary, the honest Vegas comparison |

`/[sport]` and `/[sport]/matchup/[gameId]` also render `opengraph-image.tsx`
(and a paired `twitter` card) for social previews, and are covered by the
root `sitemap.ts`/`robots.ts` (current season only, 1-hour cache).

## Commands

```powershell
npm install
npm run dev          # http://localhost:3000
npm run build        # production build
npm run start        # serve the production build
npm run lint         # eslint
npm test             # jest
npm run test:watch   # jest in watch mode
```

## Environment variables

Copy `.env.example` to `.env.local` and fill in what you need:

| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL (dev default `http://localhost:8000`) |
| `NEXT_PUBLIC_BUYMEACOFFEE_URL` | Support link; the footer button is hidden when unset |
| `NEXT_PUBLIC_USE_MOCK` | Set to `1` to serve fixture data instead of calling the backend |

## Layout

- `src/app/` routes, layout, global styles
- `src/components/` UI components, including:
  - `StatusFilter`: all/completed/upcoming chips shared by both slates;
    filter state lives in the URL (`?status=`) and survives week and
    conference navigation
  - `RecordBanner`: season-to-date model accuracy next to the market's
  - `Disagreements`: the week's largest model-vs-market probability gaps
  - `GameCard`: final score and "Called it"/"Missed" verdict badge once
    a game is played
- `src/lib/` typed API client (`api.ts`), contract types (`types.ts`),
  formatting helpers, and mock fixtures

`Disagreements` is fed a slightly different game set per sport: NFL passes
it the status-filtered week's games, while CFB passes it the
status-filtered-but-not-conference-filtered week (so picking a conference
filter doesn't shrink the disagreements panel). A defensible but
inconsistent interpretation between the two slates, not a bug.

## More

Setup for the whole project, including the backend and database, lives in
the [root README](../README.md). Backend commands are in
[backend/README.md](../backend/README.md).
