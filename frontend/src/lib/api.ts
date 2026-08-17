// Typed API client for the Blitzcast backend.
// NEXT_PUBLIC_USE_MOCK=1 serves fixture data instead of hitting the network.
// Sport is a query param on list endpoints; prediction lookups need none,
// game ids are globally unique.

import { mockGames, mockMatchup, mockSchedule, mockTeams } from "./mock";
import type { GameSummary, MatchupDetail, Schedule, Sport, Team } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

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

async function get<T>(path: string): Promise<T> {
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

export async function getMatchup(gameId: string): Promise<MatchupDetail> {
  if (MOCK) {
    const m = mockMatchup(gameId);
    if (!m) throw new NotFoundError(gameId);
    return m;
  }
  return get<MatchupDetail>(`/api/predictions/${encodeURIComponent(gameId)}`);
}
