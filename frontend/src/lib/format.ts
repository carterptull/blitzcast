import { displayAbbr } from "./teams";
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

/** Spread from the favored side: "KC -2.5", or "PK" for a pick'em.
 *  spread_home is positive when the home team is favored. */
export function fmtSpread(m: MatchupDetail): string {
  const s = m.odds?.spread_home;
  if (s == null) return "—";
  if (s === 0) return "PK";
  const favored = s > 0 ? m.home : m.away;
  const abbr = m.sport === "CFB" ? favored.abbr : displayAbbr(favored.abbr);
  return `${abbr} -${Math.abs(s)}`;
}

/**
 * Default week: the first week that still has an upcoming (or in-progress)
 * game. Before the 2026 season starts this resolves to Week 1; after the
 * finale it sticks to the last week.
 */
export function pickDefaultWeek(schedule: Schedule, now: Date = new Date()): number {
  // 12h past the last kickoff. An NFL week ends with Monday Night Football, so
  // this keeps the finished slate up overnight and rolls it Tuesday morning.
  const cutoff = now.getTime() - 12 * 60 * 60 * 1000;
  for (const w of schedule.weeks) {
    const dated = w.games.filter((g) => g.kickoff !== null);
    if (dated.some((g) => new Date(g.kickoff as string).getTime() > cutoff)) return w.week;
    // Every dated game has kicked off, so a leftover TBD does not hold the
    // week open. A week with nothing dated yet is still ahead of us.
    if (dated.length === 0 && w.games.length > 0) return w.week;
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
  // 04:00 UTC is Monday 00:00 ET; anchoring at plain UTC rolled the week over
  // on Sunday evening.
  const week1Monday = Date.UTC(2026, 7, 31, 4);
  const wk = Math.floor((now.getTime() - week1Monday) / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(wk, 1), CFB_WEEKS);
}
