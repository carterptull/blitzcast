import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ApiUnreachableError, getGames, getRecord, getSchedule, type StatusFilterValue } from "@/lib/api";
import { CFB_WEEKS, fmtDayHeading, pickCfbDefaultWeek, pickDefaultWeek } from "@/lib/format";
import { isSportSlug } from "@/lib/sport";
import type { GameSummary, Record, Schedule } from "@/lib/types";
import BackendDown from "@/components/BackendDown";
import Disagreements from "@/components/Disagreements";
import FilterChips from "@/components/FilterChips";
import GameCard from "@/components/GameCard";
import RecordBanner from "@/components/RecordBanner";
import StatusFilter from "@/components/StatusFilter";
import WeekSelector from "@/components/WeekSelector";

/** The record is secondary to the slate — never let its fetch failing take
 *  down the page. */
async function fetchRecordSafely(sport: "NFL" | "CFB"): Promise<Record | null> {
  try {
    return await getRecord(2026, sport);
  } catch {
    return null;
  }
}

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ sport: string }>;
  searchParams: Promise<{
    week?: string | string[];
    conf?: string | string[];
    top25?: string | string[];
    status?: string | string[];
  }>;
}

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

const STATUS_VALUES: readonly string[] = ["all", "final", "upcoming"];
const validStatus = (v: string | undefined): StatusFilterValue =>
  STATUS_VALUES.includes(v ?? "") ? (v as StatusFilterValue) : "all";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { sport } = await params;
  if (sport === "cfb") {
    return {
      title: "Blitzcast: College Football Win Probabilities",
      description:
        "Every 2026 college football matchup, called before kickoff. Real win probabilities, explained like a human would.",
    };
  }
  return {};
}

/** Week counter shown beside the week selector.
 *
 *  Denominator (`total`) always follows the existing "predicted" convention:
 *  every game currently displayed, regardless of grading. That doesn't
 *  change here — only the numerator and wording do.
 *
 *  When every displayed game is final, the counter switches to grading:
 *  `count` becomes the number of correctly-called verdicts
 *  (`prediction_correct === true`). A final tie or a no-pick game has
 *  `prediction_correct: null` — it's final but not graded, so it counts
 *  toward the total (it's still a displayed, finished game) but not toward
 *  the correct count. Any week with at least one non-final game keeps the
 *  original "predicted" reading. */
export function weekCounter(
  games: GameSummary[]
): { count: number; total: number; label: "predicted" | "correct" } {
  const allFinal =
    games.length > 0 && games.every((g) => g.home_score != null && g.away_score != null);
  if (allFinal) {
    return {
      count: games.filter((g) => g.prediction_correct === true).length,
      total: games.length,
      label: "correct",
    };
  }
  return {
    count: games.filter((g) => g.has_prediction).length,
    total: games.length,
    label: "predicted",
  };
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
          Win probabilities from a calibrated model, explained in plain language, never by
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

async function NflSlate({
  requestedWeek,
  status,
}: {
  requestedWeek: number;
  status: StatusFilterValue;
}) {
  const recordPromise = fetchRecordSafely("NFL");
  let schedule: Schedule;
  try {
    schedule = await getSchedule(2026, "NFL", status);
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }
  const record = await recordPromise;

  const weeks = schedule.weeks.map((w) => w.week);
  const selected = weeks.includes(requestedWeek) ? requestedWeek : pickDefaultWeek(schedule);
  const games = schedule.weeks.find((w) => w.week === selected)?.games ?? [];
  const counter = weekCounter(games);
  const filterQuery = status !== "all" ? `&status=${status}` : "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      {record && <RecordBanner record={record} />}
      <Banner season={schedule.season} week={selected} />

      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            Select a week
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-soft">
            {counter.count}/{counter.total} {counter.label}
          </span>
        </div>
        <WeekSelector weeks={weeks} selected={selected} basePath="/nfl" query={filterQuery} />
        <StatusFilter sport="nfl" active={status} week={selected} />
      </div>

      <div className="mt-8 space-y-8">
        <Disagreements games={games} sport="nfl" />
        <Slate games={games} sport="nfl" filtered={status !== "all"} />
      </div>
    </div>
  );
}

async function CfbSlate({
  requestedWeek,
  conf,
  top25,
  status,
}: {
  requestedWeek: number;
  conf?: string;
  top25: boolean;
  status: StatusFilterValue;
}) {
  const weeks = Array.from({ length: CFB_WEEKS }, (_, i) => i + 1);
  const selected = weeks.includes(requestedWeek) ? requestedWeek : pickCfbDefaultWeek();

  const recordPromise = fetchRecordSafely("CFB");
  // Per-week fetch — the CFB slate is 60+ games/week, never the whole season.
  let games: GameSummary[];
  try {
    games = await getGames(selected, 2026, "CFB", status);
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }
  const record = await recordPromise;

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
  const counter = weekCounter(filtered);
  const confQuery = `${activeConf ? `&conf=${encodeURIComponent(activeConf)}` : ""}${top25 ? "&top25=1" : ""}`;
  const statusQuery = status !== "all" ? `&status=${status}` : "";
  const filterQuery = `${confQuery}${statusQuery}`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      {record && <RecordBanner record={record} />}
      <Banner season={2026} week={selected} />

      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            Select a week
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-soft">
            {counter.count}/{counter.total} {counter.label}
          </span>
        </div>
        <WeekSelector weeks={weeks} selected={selected} basePath="/cfb" query={filterQuery} />
        <FilterChips
          conferences={conferences}
          activeConf={activeConf}
          top25={top25}
          week={selected}
          query={statusQuery}
        />
        <StatusFilter sport="cfb" active={status} week={selected} query={confQuery} />
      </div>

      <div className="mt-8 space-y-8">
        <Disagreements games={games} sport="cfb" />
        <Slate games={filtered} sport="cfb" filtered={!!activeConf || top25 || status !== "all"} />
      </div>
    </div>
  );
}

export default async function SlatePage({ params, searchParams }: Props) {
  const { sport } = await params;
  if (!isSportSlug(sport)) notFound();

  const sp = await searchParams;
  const requestedWeek = Number(one(sp.week));
  const status = validStatus(one(sp.status));

  if (sport === "cfb") {
    return (
      <CfbSlate
        requestedWeek={requestedWeek}
        conf={one(sp.conf)}
        top25={one(sp.top25) === "1"}
        status={status}
      />
    );
  }
  return <NflSlate requestedWeek={requestedWeek} status={status} />;
}
