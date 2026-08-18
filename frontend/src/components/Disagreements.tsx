import Link from "next/link";
import { fmtPct } from "@/lib/format";
import { displayAbbr } from "@/lib/teams";
import type { SportSlug } from "@/lib/sport";
import type { GameSummary } from "@/lib/types";

const MAX_SHOWN = 3;

interface Gap {
  game: GameSummary;
  homeProb: number;
  marketProb: number;
  gap: number;
}

function computeGaps(games: GameSummary[]): Gap[] {
  return games
    .filter(
      (g): g is GameSummary & { home_win_prob: number; market_home_prob: number } =>
        typeof g.home_win_prob === "number" && typeof g.market_home_prob === "number"
    )
    .map((g) => ({
      game: g,
      homeProb: g.home_win_prob,
      marketProb: g.market_home_prob,
      gap: Math.abs(g.home_win_prob - g.market_home_prob),
    }))
    .sort((a, b) => b.gap - a.gap)
    .slice(0, MAX_SHOWN);
}

/** Largest model-vs-market gaps for the displayed week. Framed as a curiosity
 *  about how the model reads a game differently than the market -- never as
 *  a signal to act on, matching the site's "not betting advice" stance. */
export default function Disagreements({
  games,
  sport,
}: {
  games: GameSummary[];
  sport: SportSlug;
}) {
  const gaps = computeGaps(games);
  if (gaps.length === 0) return null;
  const cfb = sport === "cfb";
  const abbr = (a: string) => (cfb ? a : displayAbbr(a));

  return (
    <section
      aria-label="Model vs market"
      className="rounded-xl border border-edge bg-surface p-4 sm:p-6"
    >
      <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
        Where the model reads it differently than the market
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">
        The model and the betting market don&apos;t always land in the same place. Here&apos;s
        this week&apos;s widest gaps between the model&apos;s win probability and the market&apos;s
        implied one &middot; interesting to watch, not a recommendation.
      </p>
      <div className="mt-4 space-y-2">
        {gaps.map(({ game, homeProb, marketProb, gap }) => (
          <Link
            key={game.game_id}
            href={`/${sport}/matchup/${game.game_id}`}
            className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg border border-edge px-3 py-2 text-sm transition-colors hover:border-gold/60"
          >
            <span className="font-mono uppercase tracking-wide">
              {abbr(game.away.abbr)} @ {abbr(game.home.abbr)}
            </span>
            <span className="font-mono text-xs tabular-nums text-ink-soft">
              Model {fmtPct(homeProb)} <span className="mx-1 text-edge">&middot;</span> Market{" "}
              {fmtPct(marketProb)} <span className="mx-1 text-edge">&middot;</span> {fmtPct(gap)}{" "}
              apart
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
