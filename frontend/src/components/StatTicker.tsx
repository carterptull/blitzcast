import { fmtKickoff, fmtMoneyline, fmtSpread } from "@/lib/format";
import { displayAbbr } from "@/lib/teams";
import type { MatchupDetail } from "@/lib/types";

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-r border-edge p-3 sm:p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-sm font-medium tabular-nums" title={value}>
        {value}
      </div>
    </div>
  );
}

export default function StatTicker({ matchup }: { matchup: MatchupDetail }) {
  const m = matchup;

  const weatherValue = m.venue.is_dome
    ? "Dome · controlled"
    : m.weather
      ? `${m.weather.temp_f}°F · ${m.weather.wind_mph} mph · ${m.weather.conditions}`
      : "—";

  const cells: [string, string][] = [
    ["Spread", fmtSpread(m)],
    [
      "Moneyline",
      m.odds
        ? `${displayAbbr(m.away.abbr)} ${fmtMoneyline(m.odds.moneyline_away)} / ${displayAbbr(m.home.abbr)} ${fmtMoneyline(m.odds.moneyline_home)}`
        : "—",
    ],
    ["Total", m.odds ? `O/U ${m.odds.total}` : "—"],
    ["Weather", weatherValue],
    ["Venue", m.venue.name ? `${m.venue.name} · ${m.venue.city}` : "Neutral site"],
    ["Kickoff", m.kickoff !== null ? fmtKickoff(m.kickoff) : "TBD"],
  ];

  return (
    <section aria-label="Game stats" className="overflow-hidden rounded-xl border border-edge bg-surface">
      {/* 2 cols on mobile, 3 on desktop; trailing borders trimmed via negative margin */}
      <div className="-mb-px -mr-px grid grid-cols-2 sm:grid-cols-3">
        {cells.map(([label, value]) => (
          <Cell key={label} label={label} value={value} />
        ))}
      </div>
    </section>
  );
}
