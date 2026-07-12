import type { MatchupDetail, Schedule } from "./types";

const ET = "America/New_York";

export function fmtPct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** "Thu, Sep 10 · 8:20 PM ET" */
export function fmtKickoff(iso: string): string {
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(d);
  const time = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
  return `${day} · ${time} ET`;
}

/** "8:20 PM ET" */
export function fmtKickoffTime(iso: string): string {
  const time = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
  return `${time} ET`;
}

/** "Thursday · Sep 10" — used for grouping the week slate by day. */
export function fmtDayHeading(iso: string): string {
  const d = new Date(iso);
  const weekday = new Intl.DateTimeFormat("en-US", { timeZone: ET, weekday: "long" }).format(d);
  const date = new Intl.DateTimeFormat("en-US", { timeZone: ET, month: "short", day: "numeric" }).format(d);
  return `${weekday} · ${date}`;
}

/** "Sep 8, 2026" */
export function fmtDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(iso));
}

export function fmtMoneyline(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

/** Spread from the favored side: "KC -2.5", or "PK" for a pick'em. */
export function fmtSpread(m: MatchupDetail): string {
  if (!m.odds) return "—";
  const s = m.odds.spread_home;
  if (s === 0) return "PK";
  return s < 0 ? `${m.home.abbr} ${s}` : `${m.away.abbr} -${s}`;
}

/**
 * Default week: the first week that still has an upcoming (or in-progress)
 * game. Before the 2026 season starts this resolves to Week 1; after the
 * finale it sticks to the last week.
 */
export function pickDefaultWeek(schedule: Schedule, now: Date = new Date()): number {
  const cutoff = now.getTime() - 6 * 60 * 60 * 1000; // keep a week "current" through its last kickoff
  for (const w of schedule.weeks) {
    // A TBD kickoff counts as upcoming.
    if (w.games.some((g) => g.kickoff === null || new Date(g.kickoff).getTime() > cutoff))
      return w.week;
  }
  return schedule.weeks[schedule.weeks.length - 1]?.week ?? 1;
}

export const CFB_WEEKS = 15;

/**
 * Default CFB week from the calendar (weeks roll over on Monday; Week 1 is
 * Labor Day weekend 2026). Resolves to Week 1 before the season, the finale
 * after it. Calendar-based because the CFB slate is fetched per-week.
 */
export function pickCfbDefaultWeek(now: Date = new Date()): number {
  const week1Monday = Date.UTC(2026, 7, 31);
  const wk = Math.floor((now.getTime() - week1Monday) / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(wk, 1), CFB_WEEKS);
}
