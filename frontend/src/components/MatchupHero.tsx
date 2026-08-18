import { fmtKickoff, fmtPct } from "@/lib/format";
import { displayAbbr, primaryColor } from "@/lib/teams";
import type { MatchupDetail, PredictionTeam } from "@/lib/types";
import TbdBadge from "./TbdBadge";
import TeamCrest from "./TeamCrest";
import WinProbabilitySplit from "./WinProbabilitySplit";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-sm border border-gold-turf/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-gold-turf">
      {children}
    </span>
  );
}

export function TeamColumn({
  team,
  align,
  cfb = false,
  final = false,
  score = null,
}: {
  team: PredictionTeam;
  align: "left" | "right";
  cfb?: boolean;
  final?: boolean;
  score?: number | null;
}) {
  const alignCls = align === "left" ? "sm:items-start sm:text-left" : "sm:items-end sm:text-right";
  return (
    <div className={`flex flex-col items-center gap-2 text-center ${alignCls}`}>
      <TeamCrest
        abbr={team.abbr}
        size={88}
        className="sm:size-24"
        logoUrl={cfb ? (team.logo_url ?? null) : undefined}
        color={cfb ? team.color : undefined}
        label={cfb ? team.name : undefined}
      />
      <div>
        <div className="font-display text-3xl uppercase leading-none tracking-wide sm:text-4xl">
          {team.rank != null ? (
            <span className="mr-1.5 align-middle font-mono text-base font-semibold tracking-normal text-gold-turf sm:text-lg">
              #{team.rank}
            </span>
          ) : null}
          {team.name}
        </div>
        <div className="mt-1 font-mono text-xs uppercase tracking-[0.2em] text-chalk-soft">
          {cfb ? team.abbr : displayAbbr(team.abbr)} · {team.record}
        </div>
      </div>
      <div className="mt-1">
        {final ? (
          <div className="font-display text-6xl leading-none text-chalk sm:text-7xl lg:text-8xl">
            {score}
          </div>
        ) : team.win_prob !== null ? (
          <div className="font-display text-6xl leading-none text-chalk sm:text-7xl lg:text-8xl">
            {fmtPct(team.win_prob)}
          </div>
        ) : (
          <div className="font-display text-6xl leading-none text-chalk-soft sm:text-7xl lg:text-8xl">
            —
          </div>
        )}
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-chalk-soft">
          {final ? "Final" : "Win probability"}
        </div>
      </div>
    </div>
  );
}

export default function MatchupHero({ matchup }: { matchup: MatchupDetail }) {
  const m = matchup;
  const pending = m.prediction_status !== "ready";
  const final = m.home_score != null && m.away_score != null;
  const cfb = m.sport === "CFB";
  const sport = cfb ? "CFB" : "NFL";

  return (
    <section className="turf overflow-hidden rounded-2xl">
      <div className="px-5 py-8 sm:px-10 sm:py-12">
        <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 font-mono text-[11px] uppercase tracking-[0.18em] text-chalk-soft sm:justify-start">
          <span className="text-gold-turf">Week {m.week}</span>
          <span aria-hidden="true">·</span>
          {m.kickoff !== null ? (
            <span className="tabular-nums">{fmtKickoff(m.kickoff)}</span>
          ) : (
            <TbdBadge onTurf />
          )}
          <span aria-hidden="true">·</span>
          <span>{m.venue.name ? `${m.venue.name}, ${m.venue.city}` : "Neutral site"}</span>
          {m.is_primetime ? <Badge>Prime time</Badge> : null}
          {m.is_divisional ? <Badge>{cfb ? "Conference game" : "Divisional"}</Badge> : null}
          {final ? <Badge>Final</Badge> : null}
        </div>

        <div className="mt-8 grid items-center gap-8 sm:grid-cols-[1fr_auto_1fr] sm:gap-6">
          <TeamColumn team={m.away} align="left" cfb={cfb} final={final} score={m.away_score} />
          {/* Center mark; hidden on mobile */}
          <div className="hidden flex-col items-center gap-1 sm:flex" aria-hidden="true">
            <span className="font-display text-2xl uppercase text-chalk-soft">at</span>
            <svg viewBox="0 0 12 12" className="size-2 text-gold-turf">
              <path d="M6 0 12 12 0 12z" fill="currentColor" />
            </svg>
          </div>
          <TeamColumn team={m.home} align="right" cfb={cfb} final={final} score={m.home_score} />
        </div>

        <div className="mt-8">
          {final ? (
            <div className="rounded-md border border-chalk-soft/25 p-3">
              {m.prediction_correct !== null ? (
                <p
                  className={`text-center font-mono text-[11px] uppercase tracking-[0.2em] ${
                    m.prediction_correct ? "text-verdict-hit-turf" : "text-verdict-miss-turf"
                  }`}
                >
                  {m.prediction_correct ? "Model called it" : "Model missed"}
                </p>
              ) : (
                <p className="text-center font-mono text-[11px] uppercase tracking-[0.2em] text-chalk-soft">
                  Final: no prediction on record for this one
                </p>
              )}
            </div>
          ) : !pending && m.away.win_prob !== null && m.home.win_prob !== null ? (
            <>
              <WinProbabilitySplit
                away={{
                  abbr: m.away.abbr,
                  prob: m.away.win_prob,
                  color: cfb ? primaryColor(sport, m.away.abbr, m.away.color) : undefined,
                }}
                home={{
                  abbr: m.home.abbr,
                  prob: m.home.win_prob,
                  color: cfb ? primaryColor(sport, m.home.abbr, m.home.color) : undefined,
                }}
              />
              <div className="mt-2 flex justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-chalk-soft">
                <span>{cfb ? m.away.abbr : displayAbbr(m.away.abbr)}</span>
                <span>{cfb ? m.home.abbr : displayAbbr(m.home.abbr)}</span>
              </div>
            </>
          ) : (
            <div className="rounded-md border border-chalk-soft/25">
              <div className="hatch flex h-10 items-center justify-center rounded-md">
                <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-chalk-soft">
                  Prediction pending: runs after the weekly data refresh
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
