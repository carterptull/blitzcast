// Mock-mode slates built from a mock schedule. Mirrors the backend's build_slates
// (backend/app/services/predictions.py) so mock and live strips behave the same.

import { ROUNDS } from "./occasion";
import type { GameSummary, Round, Schedule, Slate } from "./types";

const GRACE_MS = 12 * 60 * 60 * 1000;

const SLUGS: Partial<Record<Round, string>> = {
  wild_card: "wild-card",
  divisional: "divisional",
  conference: "conference",
  super_bowl: "super-bowl",
  bowl: "bowls",
  cfp_first_round: "cfp-first-round",
  cfp_quarterfinal: "cfp-quarterfinals",
  cfp_semifinal: "cfp-semifinals",
  cfp_championship: "cfp-title",
  cfp_other: "cfp-other",
};

const LABELS: Record<Round, [string, string, string | null]> = {
  conf_championship: ["Conference Championships", "Champ", null],
  wild_card: ["Wild Card", "Round", "WC"],
  divisional: ["Divisional", "Round", "DIV"],
  conference: ["Conference Championships", "Round", "CONF"],
  super_bowl: ["Super Bowl", "Round", "SB"],
  bowl: ["Bowl Season", "Non-CFP", "Bowls"],
  cfp_first_round: ["CFP First Round", "CFP", "R1"],
  cfp_quarterfinal: ["CFP Quarterfinals", "CFP", "QF"],
  cfp_semifinal: ["CFP Semifinals", "CFP", "SF"],
  cfp_championship: ["National Championship", "CFP", "Title"],
  cfp_other: ["College Football Playoff", "CFP", "CFP"],
};

function window(games: GameSummary[], now: Date) {
  const kicks = games
    .map((g) => g.kickoff)
    .filter((k): k is string => k !== null)
    .sort();
  const upcoming = kicks.filter((k) => new Date(k).getTime() > now.getTime() - GRACE_MS);
  return {
    game_count: games.length,
    first_kickoff: kicks[0] ?? null,
    last_kickoff: kicks[kicks.length - 1] ?? null,
    next_kickoff: upcoming[0] ?? null,
    has_unscheduled: games.some(
      (g) => g.kickoff === null && g.home_score === null && g.away_score === null
    ),
  };
}

export function slatesFromSchedule(schedule: Schedule, now: Date = new Date()): Slate[] {
  const regular = new Map<number, GameSummary[]>();
  const post = new Map<Round, { week: number; games: GameSummary[] }>();
  for (const w of schedule.weeks) {
    for (const g of w.games) {
      if (g.season_type === "postseason") {
        const r = g.round ?? "cfp_other";
        const entry = post.get(r) ?? { week: w.week, games: [] };
        entry.week = Math.min(entry.week, w.week);
        entry.games.push(g);
        post.set(r, entry);
      } else {
        regular.set(w.week, [...(regular.get(w.week) ?? []), g]);
      }
    }
  }
  const slates: Slate[] = [];
  for (const week of [...regular.keys()].sort((a, b) => a - b)) {
    const games = regular.get(week)!;
    const champ = games.some((g) => g.round === "conf_championship");
    slates.push({
      key: `w${week}`,
      phase: "regular",
      week,
      round: null,
      label: champ ? LABELS.conf_championship[0] : null,
      group_label: champ ? LABELS.conf_championship[1] : "Wk",
      short_label: String(week),
      ...window(games, now),
    });
  }
  for (const r of ROUNDS) {
    const entry = post.get(r);
    const slug = SLUGS[r];
    if (!entry || !slug) continue;
    const [label, group, short] = LABELS[r];
    slates.push({
      key: slug,
      phase: "postseason",
      week: entry.week,
      round: r,
      label,
      group_label: group,
      short_label: short ?? label,
      ...window(entry.games, now),
    });
  }
  return slates;
}

/** Round slug -> round, for filtering mock games. */
export function roundForSlug(slug: string): Round | null {
  const hit = (Object.entries(SLUGS) as [Round, string][]).find(([, s]) => s === slug);
  return hit ? hit[0] : null;
}
