// Typed API client for the Blitzcast backend.
// NEXT_PUBLIC_USE_MOCK=1 serves fixture data instead of hitting the network.
// Sport is a query param on list endpoints; prediction lookups need none,
// game ids are globally unique.

import { unstable_cache } from "next/cache";
import { mockGames, mockMatchup, mockSchedule, mockTeams } from "./mock";
import type { GameSummary, MatchupDetail, Record, Schedule, Sport, Team } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";
const FRESH_WINDOW_MS = 5 * 60 * 1000;

export class ApiUnreachableError extends Error {
  constructor(detail?: string) {
    super(detail ?? `Could not reach the Blitzcast API at ${BASE}`);
    this.name = "ApiUnreachableError";
  }
}

export class NotFoundError extends Error {
  constructor(what: string) {
    super(`Not found: ${what}`);
    this.name = "NotFoundError";
  }
}

/** Mirrors the backend's status filter (Query("all"), normalized server-side
 *  — unrecognized values fall back to "all"). */
export type StatusFilterValue = "all" | "final" | "upcoming";

async function fetchJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiUnreachableError();
  }
  if (res.status === 404) throw new NotFoundError(path);
  if (!res.ok) throw new ApiUnreachableError(`API responded ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

// unstable_cache serves repeat week clicks from cache for 30s, but it hands
// back a stale entry however old. Keying on the clock window forces a blocking
// fresh fetch once a window rolls over, so data is never older than the window.
// Thrown errors are not cached.
async function get<T>(path: string): Promise<T> {
  const window = Math.floor(Date.now() / FRESH_WINDOW_MS);
  return unstable_cache(() => fetchJson<T>(path), ["api", path, String(window)], {
    revalidate: 30,
  })();
}

export async function getTeams(sport: Sport = "NFL"): Promise<Team[]> {
  if (MOCK) return mockTeams(sport);
  return get<Team[]>(`/api/teams?sport=${sport}`);
}

export async function getSchedule(
  season = 2026,
  sport: Sport = "NFL",
  status: StatusFilterValue = "all"
): Promise<Schedule> {
  if (MOCK) return mockSchedule(sport);
  return get<Schedule>(`/api/schedule?season=${season}&sport=${sport}&status=${status}`);
}

export async function getGames(
  week: number,
  season = 2026,
  sport: Sport = "NFL",
  status: StatusFilterValue = "all"
): Promise<GameSummary[]> {
  if (MOCK) return mockGames(week, sport);
  return get<GameSummary[]>(
    `/api/games?week=${week}&season=${season}&sport=${sport}&status=${status}`
  );
}

export async function getRecord(season = 2026, sport: Sport = "NFL"): Promise<Record> {
  if (MOCK) {
    // Demo fixture — deliberately shows the model trailing the market, same
    // as the real record does, rather than an implausibly clean number.
    return { sport, season, correct: 11, total: 16, market_correct: 12, sufficient: true };
  }
  return get<Record>(`/api/record?sport=${sport}&season=${season}`);
}

/** Same rule as the backend (Game.game_id is String(32)). */
export function isGameId(id: string): boolean {
  return /^[A-Za-z0-9_-]{1,32}$/.test(id);
}

export async function getMatchup(gameId: string): Promise<MatchupDetail> {
  if (!isGameId(gameId)) throw new NotFoundError(gameId);
  if (MOCK) {
    const m = mockMatchup(gameId);
    if (!m) throw new NotFoundError(gameId);
    return m;
  }
  return get<MatchupDetail>(`/api/predictions/${encodeURIComponent(gameId)}`);
}
