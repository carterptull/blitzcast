import { displayAbbr } from "./teams";
import type { MatchupDetail, Slate } from "./types";

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
  if (s == null) return "N/A";
  if (s === 0) return "PK";
  const favored = s > 0 ? m.home : m.away;
  const abbr = m.sport === "CFB" ? favored.abbr : displayAbbr(favored.abbr);
  return `${abbr} -${Math.abs(s)}`;
}

const CFP_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

const nextKickoffMs = (s: Slate) =>
  s.next_kickoff !== null ? Date.parse(s.next_kickoff) : Number.POSITIVE_INFINITY;

const soonest = (slates: Slate[]) =>
  slates.reduce((best, s) => (nextKickoffMs(s) < nextKickoffMs(best) ? s : best));

/**
 * Default slate on first load. Once any postseason slate exists only those
 * are candidates. A CFP round kicking off within 7 days wins; otherwise the
 * live slate with the soonest kickoff, with unscheduled-only slates last;
 * otherwise the last candidate.
 */
export function pickDefaultSlate(slates: Slate[], now: Date = new Date()): Slate | undefined {
  const post = slates.filter((s) => s.phase === "postseason");
  const candidates = post.length > 0 ? post : slates;
  const live = candidates.filter((s) => s.next_kickoff !== null || s.has_unscheduled);
  const cfpSoon = live.filter(
    (s) => s.round?.startsWith("cfp_") && nextKickoffMs(s) - now.getTime() <= CFP_WINDOW_MS
  );
  if (cfpSoon.length > 0) return soonest(cfpSoon);
  if (live.length > 0) return soonest(live);
  return candidates[candidates.length - 1];
}

/** `?week=N` opens a regular week, `?round=slug` a postseason slate; anything
 *  else falls back to the default. */
export function resolveSlate(
  slates: Slate[],
  params: { week?: string; round?: string },
  now: Date = new Date()
): Slate | undefined {
  const { week, round } = params;
  const byRound = round
    ? slates.find((s) => s.phase === "postseason" && s.key === round)
    : undefined;
  if (byRound) return byRound;
  const byWeek =
    week && /^\d{1,2}$/.test(week)
      ? slates.find((s) => s.phase === "regular" && s.week === Number(week))
      : undefined;
  return byWeek ?? pickDefaultSlate(slates, now);
}

/** "week=5" or "round=bowls". */
export function slateQuery(slate: Slate): string {
  return slate.phase === "postseason" ? `round=${slate.key}` : `week=${slate.week}`;
}

export function slateHref(basePath: string, slate: Slate, query = ""): string {
  return `${basePath}?${slateQuery(slate)}${query}`;
}

/** "2026 Season · Week 12" or "2026 Postseason · Wild Card". */
export function eyebrowText(season: number, slate: Slate): string {
  if (slate.phase === "postseason") return `${season} Postseason · ${slate.label ?? slate.short_label}`;
  return `${season} Season · ${slate.label ?? `Week ${slate.week}`}`;
}
