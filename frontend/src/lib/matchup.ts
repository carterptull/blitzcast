// Matchup page wording: separator, title and back link.

import type { SportSlug } from "./sport";
import { displayAbbr } from "./teams";
import type { MatchupDetail, Round } from "./types";

/** Postseason round -> [slate slug, label]. Mirrors backend app/postseason.py. */
const ROUND_SLATES: Partial<Record<Round, [string, string]>> = {
  wild_card: ["wild-card", "Wild Card"],
  divisional: ["divisional", "Divisional"],
  conference: ["conference", "Conference Championships"],
  super_bowl: ["super-bowl", "Super Bowl"],
  bowl: ["bowls", "Bowl Season"],
  cfp_first_round: ["cfp-first-round", "CFP First Round"],
  cfp_quarterfinal: ["cfp-quarterfinals", "CFP Quarterfinals"],
  cfp_semifinal: ["cfp-semifinals", "CFP Semifinals"],
  cfp_championship: ["cfp-title", "National Championship"],
  cfp_other: ["cfp-other", "College Football Playoff"],
};

export function matchupSeparator(neutral: boolean): "vs" | "@" {
  return neutral ? "vs" : "@";
}

/** The game's own name, or "Week N" for an ordinary game. */
export function occasionLabel(m: Pick<MatchupDetail, "event_name" | "week">): string {
  return m.event_name ?? `Week ${m.week}`;
}

export function matchupTitle(m: MatchupDetail): string {
  const cfb = m.sport === "CFB";
  const away = cfb ? m.away.abbr : displayAbbr(m.away.abbr);
  const home = cfb ? m.home.abbr : displayAbbr(m.home.abbr);
  return `${away} ${matchupSeparator(m.venue.is_neutral_site)} ${home}, ${occasionLabel(m)}`;
}

export function backLink(m: MatchupDetail, sport: SportSlug): { href: string; label: string } {
  const slate = m.season_type === "postseason" && m.round ? ROUND_SLATES[m.round] : undefined;
  if (slate) return { href: `/${sport}?round=${slate[0]}`, label: `Back to ${slate[1]}` };
  return { href: `/${sport}?week=${m.week}`, label: `Week ${m.week} slate` };
}
