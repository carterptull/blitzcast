import Link from "next/link";
import { fmtKickoffTime, fmtPct } from "@/lib/format";
import { apiSport, type SportSlug } from "@/lib/sport";
import { displayAbbr, primaryColor } from "@/lib/teams";
import type { GameSummary, GameTeamRef } from "@/lib/types";
import TbdBadge from "./TbdBadge";
import TeamCrest from "./TeamCrest";

function TeamRow({
  team,
  cfb,
  prob,
  favored,
}: {
  team: GameTeamRef;
  cfb: boolean;
  prob: number | null;
  favored: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <TeamCrest
        abbr={team.abbr}
        size={34}
        logoUrl={cfb ? (team.logo_url ?? null) : undefined}
        color={cfb ? team.color : undefined}
        label={cfb ? team.name : undefined}
      />
      <span className="font-display text-xl uppercase leading-none tracking-wide">
        {cfb ? team.abbr : displayAbbr(team.abbr)}
      </span>
      {team.rank != null ? (
        <span className="-ml-1.5 font-mono text-[10px] font-semibold tabular-nums text-gold-text">
          #{team.rank}
        </span>
      ) : null}
      <span className="truncate text-sm text-ink-soft">{team.name}</span>
      {prob !== null ? (
        <span
          className={`ml-auto font-mono text-sm font-semibold tabular-nums ${
            favored ? "text-gold-text" : "text-ink-soft"
          }`}
        >
          {fmtPct(prob)}
        </span>
      ) : null}
    </div>
  );
}

export default function GameCard({
  game,
  sport = "nfl",
}: {
  game: GameSummary;
  sport?: SportSlug;
}) {
  const cfb = sport === "cfb";
  const s = apiSport(sport);
  const homeProb = typeof game.home_win_prob === "number" ? game.home_win_prob : null;
  const awayProb = homeProb === null ? null : 1 - homeProb;
  const awayColor = primaryColor(s, game.away.abbr, game.away.color);
  const homeColor = primaryColor(s, game.home.abbr, game.home.color);

  return (
    <Link
      href={`/${sport}/matchup/${game.game_id}`}
      className="group block rounded-xl border border-edge bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-gold/60 hover:shadow-lg hover:shadow-stripe-a/10 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <div className="space-y-2.5">
        <TeamRow
          team={game.away}
          cfb={cfb}
          prob={awayProb}
          favored={awayProb !== null && awayProb > 0.5}
        />
        <TeamRow
          team={game.home}
          cfb={cfb}
          prob={homeProb}
          favored={homeProb !== null && homeProb > 0.5}
        />
      </div>

      {/* Compact win-prob split, or an intentional pending strip */}
      {awayProb !== null ? (
        <div
          className="mt-3 flex h-1.5 overflow-hidden rounded-full"
          aria-hidden="true"
          style={{ boxShadow: "inset 0 0 0 1px rgba(128,128,128,0.15)" }}
        >
          <div style={{ width: `${awayProb * 100}%`, background: awayColor }} />
          <div className="w-[2px] shrink-0 bg-gold" />
          <div className="flex-1" style={{ background: homeColor }} />
        </div>
      ) : (
        <div className="hatch mt-3 h-1.5 rounded-full border border-edge" aria-hidden="true" />
      )}

      <div className="mt-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-ink-soft">
        {game.kickoff !== null ? (
          <span className="tabular-nums">{fmtKickoffTime(game.kickoff)}</span>
        ) : (
          <TbdBadge />
        )}
        {game.is_primetime ? (
          <span className="rounded-sm border border-gold/50 px-1.5 py-0.5 text-[9px] tracking-[0.15em] text-gold-text">
            Prime time
          </span>
        ) : null}
        {!game.has_prediction ? (
          <span className="ml-auto text-[9px] tracking-[0.15em]">Prediction pending</span>
        ) : (
          <span className="ml-auto text-gold-text opacity-0 transition-opacity group-hover:opacity-100 motion-reduce:transition-none">
            →
          </span>
        )}
      </div>
    </Link>
  );
}
