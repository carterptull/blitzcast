// Pure content-shaping logic for the matchup OG share image. Split out from
// opengraph-image.tsx (which imports next/og and renders via satori) so the
// branchy "what does this card say" logic is unit-testable without needing
// to exercise the ImageResponse/satori rendering pipeline.

import { fmtPct } from "./format";
import { displayAbbr } from "./teams";
import type { MatchupDetail } from "./types";

export interface OgTeamContent {
  abbr: string;
  /** Score (final), win-prob percentage (ready), or "—" (pending). */
  value: string;
  /** Winning side (final) or favored side (ready), styled in gold. */
  highlight: boolean;
}

export interface OgContent {
  away: OgTeamContent;
  home: OgTeamContent;
  final: boolean;
  hasProbs: boolean;
  /** "Final" or "Win probability", shown under both team blocks. */
  sub: string;
  /** "Model called it" / "Model missed", only set for a final game with a
   *  prediction on record. */
  verdictText: string | null;
  verdictHit: boolean | null;
  /** Not final and no prediction yet. */
  pending: boolean;
  week: number;
  season: number;
  league: string;
  cfb: boolean;
}

export function buildOgContent(m: MatchupDetail): OgContent {
  const cfb = m.sport === "CFB";
  const league = cfb ? "College Football" : "NFL";
  const awayAbbr = cfb ? m.away.abbr : displayAbbr(m.away.abbr);
  const homeAbbr = cfb ? m.home.abbr : displayAbbr(m.home.abbr);
  const final = m.home_score !== null && m.away_score !== null;
  const hasProbs = m.away.win_prob !== null && m.home.win_prob !== null;

  const awayValue = final
    ? String(m.away_score)
    : hasProbs
      ? fmtPct(m.away.win_prob as number)
      : "—";
  const homeValue = final
    ? String(m.home_score)
    : hasProbs
      ? fmtPct(m.home.win_prob as number)
      : "—";
  const awayHighlight = final
    ? (m.away_score as number) > (m.home_score as number)
    : hasProbs && (m.away.win_prob as number) > 0.5;
  const homeHighlight = final
    ? (m.home_score as number) > (m.away_score as number)
    : hasProbs && (m.home.win_prob as number) > 0.5;

  const verdictText =
    m.prediction_correct === null ? null : m.prediction_correct ? "Model called it" : "Model missed";

  return {
    away: { abbr: awayAbbr, value: awayValue, highlight: awayHighlight },
    home: { abbr: homeAbbr, value: homeValue, highlight: homeHighlight },
    final,
    hasProbs,
    sub: final ? "Final" : "Win probability",
    verdictText: final ? verdictText : null,
    verdictHit: m.prediction_correct,
    pending: !final && !hasProbs,
    week: m.week,
    season: m.season,
    league,
    cfb,
  };
}
