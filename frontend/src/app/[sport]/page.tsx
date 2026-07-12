import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ApiUnreachableError, getGames, getSchedule } from "@/lib/api";
import { CFB_WEEKS, fmtDayHeading, pickCfbDefaultWeek, pickDefaultWeek } from "@/lib/format";
import { isSportSlug } from "@/lib/sport";
import type { GameSummary, Schedule } from "@/lib/types";
import BackendDown from "@/components/BackendDown";
import FilterChips from "@/components/FilterChips";
import GameCard from "@/components/GameCard";
import WeekSelector from "@/components/WeekSelector";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ sport: string }>;
  searchParams: Promise<{
    week?: string | string[];
    conf?: string | string[];
    top25?: string | string[];
  }>;
}

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { sport } = await params;
  if (sport === "cfb") {
    return {
      title: "Blitzcast — College Football Win Probabilities",
      description:
        "AI-powered win probabilities with plain-language reasoning for every 2026 college football matchup.",
    };
  }
  return {};
}

function groupByDay(games: GameSummary[]): [string, GameSummary[]][] {
  // TBD kickoffs sort and group last.
  const sorted = [...games].sort((a, b) =>
    (a.kickoff ?? "9999").localeCompare(b.kickoff ?? "9999")
  );
  const groups = new Map<string, GameSummary[]>();
  for (const g of sorted) {
    const key = g.kickoff !== null ? fmtDayHeading(g.kickoff) : "Kickoff TBD";
    const list = groups.get(key) ?? [];
    list.push(g);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

function Banner({ season, week }: { season: number; week: number }) {
  return (
    <section className="turf overflow-hidden rounded-2xl">
      <div className="px-6 py-10 sm:px-10 sm:py-14">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-gold-turf">
          {season} Season · Week {week}
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
  );
}

function Slate({ games, sport, filtered }: { games: GameSummary[]; sport: "nfl" | "cfb"; filtered: boolean }) {
  if (games.length === 0) {
    return (
      <p className="py-16 text-center italic text-ink-soft">
        {filtered ? "No games match these filters." : "No games scheduled for this week."}
      </p>
    );
  }
  return (
    <>
      {groupByDay(games).map(([day, dayGames]) => (
        <section key={day}>
          <h3 className="mb-3 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            {day}
            <span className="h-px flex-1 bg-edge" aria-hidden="true" />
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {dayGames.map((g) => (
              <GameCard key={g.game_id} game={g} sport={sport} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

async function NflSlate({ requestedWeek }: { requestedWeek: number }) {
  let schedule: Schedule;
  try {
    schedule = await getSchedule(2026, "NFL");
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }

  const weeks = schedule.weeks.map((w) => w.week);
  const selected = weeks.includes(requestedWeek) ? requestedWeek : pickDefaultWeek(schedule);
  const games = schedule.weeks.find((w) => w.week === selected)?.games ?? [];
  const predicted = games.filter((g) => g.has_prediction).length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Banner season={schedule.season} week={selected} />

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
        <WeekSelector weeks={weeks} selected={selected} basePath="/nfl" />
      </div>

      {/* Slate, grouped by day */}
      <div className="mt-8 space-y-8">
        <Slate games={games} sport="nfl" filtered={false} />
      </div>
    </div>
  );
}

async function CfbSlate({
  requestedWeek,
  conf,
  top25,
}: {
  requestedWeek: number;
  conf?: string;
  top25: boolean;
}) {
  const weeks = Array.from({ length: CFB_WEEKS }, (_, i) => i + 1);
  const selected = weeks.includes(requestedWeek) ? requestedWeek : pickCfbDefaultWeek();

  // Per-week fetch — the CFB slate is 60+ games/week, never the whole season.
  let games: GameSummary[];
  try {
    games = await getGames(selected, 2026, "CFB");
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }

  const conferences = [
    ...new Set(
      games
        .flatMap((g) => [g.home.conference, g.away.conference])
        .filter((c): c is string => !!c)
    ),
  ].sort();
  const activeConf = conf && conferences.includes(conf) ? conf : null;

  const filtered = games.filter((g) => {
    if (activeConf && g.home.conference !== activeConf && g.away.conference !== activeConf)
      return false;
    if (top25 && g.home.rank == null && g.away.rank == null) return false;
    return true;
  });
  const predicted = filtered.filter((g) => g.has_prediction).length;
  const filterQuery = `${activeConf ? `&conf=${encodeURIComponent(activeConf)}` : ""}${top25 ? "&top25=1" : ""}`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Banner season={2026} week={selected} />

      {/* Week selector + filter chips */}
      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            Select a week
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-soft">
            {predicted}/{filtered.length} predicted
          </span>
        </div>
        <WeekSelector weeks={weeks} selected={selected} basePath="/cfb" query={filterQuery} />
        <FilterChips
          conferences={conferences}
          activeConf={activeConf}
          top25={top25}
          week={selected}
        />
      </div>

      {/* Slate, grouped by day */}
      <div className="mt-8 space-y-8">
        <Slate games={filtered} sport="cfb" filtered={!!activeConf || top25} />
      </div>
    </div>
  );
}

export default async function SlatePage({ params, searchParams }: Props) {
  const { sport } = await params;
  if (!isSportSlug(sport)) notFound();

  const sp = await searchParams;
  const requestedWeek = Number(one(sp.week));

  if (sport === "cfb") {
    return <CfbSlate requestedWeek={requestedWeek} conf={one(sp.conf)} top25={one(sp.top25) === "1"} />;
  }
  return <NflSlate requestedWeek={requestedWeek} />;
}
