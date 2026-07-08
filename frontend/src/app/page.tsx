import { ApiUnreachableError, getSchedule } from "@/lib/api";
import { fmtDayHeading, pickDefaultWeek } from "@/lib/format";
import type { GameSummary, Schedule } from "@/lib/types";
import BackendDown from "@/components/BackendDown";
import GameCard from "@/components/GameCard";
import WeekSelector from "@/components/WeekSelector";

export const dynamic = "force-dynamic";

function groupByDay(games: GameSummary[]): [string, GameSummary[]][] {
  const sorted = [...games].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  const groups = new Map<string, GameSummary[]>();
  for (const g of sorted) {
    const key = fmtDayHeading(g.kickoff);
    const list = groups.get(key) ?? [];
    list.push(g);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ week?: string | string[] }>;
}) {
  const sp = await searchParams;

  let schedule: Schedule;
  try {
    schedule = await getSchedule(2026);
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }

  const weeks = schedule.weeks.map((w) => w.week);
  const requested = Number(Array.isArray(sp.week) ? sp.week[0] : sp.week);
  const selected = weeks.includes(requested) ? requested : pickDefaultWeek(schedule);
  const games = schedule.weeks.find((w) => w.week === selected)?.games ?? [];
  const predicted = games.filter((g) => g.has_prediction).length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      {/* Turf banner */}
      <section className="turf overflow-hidden rounded-2xl">
        <div className="px-6 py-10 sm:px-10 sm:py-14">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-gold-turf">
            {schedule.season} Season · Week {selected}
          </p>
          <h1 className="mt-2 max-w-2xl font-display text-4xl uppercase leading-[0.95] tracking-wide text-chalk sm:text-6xl">
            Every matchup, called before kickoff
          </h1>
          <p className="mt-4 max-w-xl text-lg italic leading-relaxed text-chalk-soft">
            Win probabilities from a calibrated model — explained in plain language, never by
            guesswork.
          </p>
        </div>
      </section>

      {/* Week selector */}
      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            Select a week
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-soft">
            {predicted}/{games.length} predicted
          </span>
        </div>
        <WeekSelector weeks={weeks} selected={selected} />
      </div>

      {/* Slate, grouped by day */}
      <div className="mt-8 space-y-8">
        {games.length === 0 ? (
          <p className="py-16 text-center italic text-ink-soft">
            No games scheduled for this week.
          </p>
        ) : (
          groupByDay(games).map(([day, dayGames]) => (
            <section key={day}>
              <h3 className="mb-3 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
                {day}
                <span className="h-px flex-1 bg-edge" aria-hidden="true" />
              </h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {dayGames.map((g) => (
                  <GameCard key={g.game_id} game={g} />
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </div>
  );
}
