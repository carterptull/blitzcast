// Typed API client for the Blitzcast backend (IMPLEMENTATION_PLAN.md §3.2).
// NEXT_PUBLIC_USE_MOCK=1 serves fixture data instead of hitting the network.

import { mockGames, mockMatchup, mockSchedule, mockTeams } from "./mock";
import type { GameSummary, MatchupDetail, Schedule, Team } from "./types";

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

export async function getTeams(): Promise<Team[]> {
  if (MOCK) return mockTeams();
  return get<Team[]>("/api/teams");
}

export async function getSchedule(season = 2026): Promise<Schedule> {
  if (MOCK) return mockSchedule();
  return get<Schedule>(`/api/schedule?season=${season}`);
}

export async function getGames(week: number, season = 2026): Promise<GameSummary[]> {
  if (MOCK) return mockGames(week);
  return get<GameSummary[]>(`/api/games?week=${week}&season=${season}`);
}

export async function getMatchup(gameId: string): Promise<MatchupDetail> {
  if (MOCK) {
    const m = mockMatchup(gameId);
    if (!m) throw new NotFoundError(gameId);
    return m;
  }
  return get<MatchupDetail>(`/api/predictions/${encodeURIComponent(gameId)}`);
}
