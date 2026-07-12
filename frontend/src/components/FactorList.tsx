import { primaryColor, textOn } from "@/lib/teams";
import type { Factor, MatchupDetail } from "@/lib/types";

/**
 * Signed, labeled SHAP factors. Each row shows which team the factor favors
 * (team-color chip), the human label, a magnitude bar in that team's color,
 * and the mono weight. Renders fine with narrative null — it is the fallback
 * story when prose is unavailable.
 */
export default function FactorList({ matchup }: { matchup: MatchupDetail }) {
  const m = matchup;
  if (m.factors.length === 0) return null;
  const maxAbs = Math.max(...m.factors.map((x) => Math.abs(x.value)));

  return (
    <ol className="space-y-3">
      {m.factors.map((factor: Factor, i: number) => {
        const team = factor.direction === "home" ? m.home : m.away;
        const color = primaryColor(m.sport ?? "NFL", team.abbr, team.color);
        const abs = Math.abs(factor.value);
        return (
          <li key={`${factor.label}-${i}`} className="grid grid-cols-[2.75rem_1fr_auto] items-center gap-3">
            <span
              className="rounded-sm py-0.5 text-center font-mono text-[10px] font-semibold uppercase tracking-wider"
              style={{ background: color, color: textOn(color) }}
              title={`Favors ${team.name}`}
            >
              {team.abbr}
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm" title={factor.label}>
                {factor.label}
              </div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-edge" aria-hidden="true">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${(abs / maxAbs) * 100}%`, background: color }}
                />
              </div>
            </div>
            <span className="font-mono text-sm font-medium tabular-nums text-gold-text">
              +{abs.toFixed(2)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
