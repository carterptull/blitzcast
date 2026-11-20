import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import {
  ApiUnreachableError,
  getGames,
  getRecord,
  getSchedule,
  getSlates,
  type StatusFilterValue,
} from "@/lib/api";
import {
  eyebrowText,
  fmtDayHeading,
  pickDefaultSlate,
  resolveSlate,
  slateHref,
  slateQuery,
} from "@/lib/format";
import { isSportSlug } from "@/lib/sport";
import type { GameSummary, Record, Schedule, Slate } from "@/lib/types";
import BackendDown from "@/components/BackendDown";
import Disagreements from "@/components/Disagreements";
import FilterChips from "@/components/FilterChips";
import GameCard from "@/components/GameCard";
import PhaseToggle from "@/components/PhaseToggle";
import RecordBanner from "@/components/RecordBanner";
import StatusFilter from "@/components/StatusFilter";
import SlateSelector from "@/components/SlateSelector";

/** The record is secondary to the slate — never let its fetch failing take
 *  down the page. */
async function fetchRecordSafely(sport: "NFL" | "CFB"): Promise<Record | null> {
  try {
    return await getRecord(2026, sport);
  } catch {
    return null;
  }
}

interface Props {
  params: Promise<{ sport: string }>;
  searchParams: Promise<{
    week?: string | string[];
    round?: string | string[];
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

function Banner({ eyebrow }: { eyebrow: string }) {
  return (
    <section className="turf overflow-hidden rounded-2xl">
      <div className="px-6 py-10 sm:px-10 sm:py-14">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-gold-turf">
          {eyebrow}
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

function SlateGames({
  games,
  sport,
  filtered,
  postseason,
}: {
  games: GameSummary[];
  sport: "nfl" | "cfb";
  filtered: boolean;
  postseason: boolean;
}) {
  if (games.length === 0) {
    return (
      <p className="py-16 text-center italic text-ink-soft">
        {filtered
          ? "No games match these filters."
          : postseason
            ? "Matchups are set as each round is decided."
            : "No games scheduled for this week."}
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

/** Banner, phase toggle and slate strip shared by both sports. The strip
 *  lists only the active phase's slates. */
function SlateHeader({
  sport,
  season,
  slates,
  slate,
  record,
  counter,
  query,
  statusQuery,
  children,
}: {
  sport: "nfl" | "cfb";
  season: number;
  slates: Slate[];
  slate: Slate | undefined;
  record: Record | null;
  counter: ReturnType<typeof weekCounter>;
  query: string;
  statusQuery: string;
  children: ReactNode;
}) {
  const basePath = `/${sport}`;
  const phase = slate?.phase ?? "regular";
  const regular = slates.filter((s) => s.phase === "regular");
  const post = slates.filter((s) => s.phase === "postseason");
  const regularDefault = pickDefaultSlate(regular);
  const postDefault = pickDefaultSlate(post);

  return (
    <>
      {record && <RecordBanner record={record} />}
      <Banner eyebrow={slate ? eyebrowText(season, slate) : `${season} Season`} />
      <PhaseToggle
        phase={phase}
        regularHref={regularDefault ? slateHref(basePath, regularDefault, statusQuery) : basePath}
        postseasonHref={postDefault ? slateHref(basePath, postDefault, statusQuery) : null}
      />

      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            {phase === "postseason" ? "Select a round" : "Select a week"}
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-soft">
            {counter.count}/{counter.total} {counter.label}
          </span>
        </div>
        <SlateSelector
          slates={phase === "postseason" ? post : regular}
          selectedKey={slate?.key ?? ""}
          basePath={basePath}
          query={query}
        />
        {children}
      </div>
    </>
  );
}

async function NflSlate({
  requested,
  status,
}: {
  requested: { week?: string; round?: string };
  status: StatusFilterValue;
}) {
  const recordPromise = fetchRecordSafely("NFL");
  let slates: Slate[];
  let schedule: Schedule;
  try {
    [slates, schedule] = await Promise.all([getSlates(2026, "NFL"), getSchedule(2026, "NFL", status)]);
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }
  const record = await recordPromise;

  const slate = resolveSlate(slates, requested);
  const games = slate ? (schedule.weeks.find((w) => w.week === slate.week)?.games ?? []) : [];
  const statusQuery = status !== "all" ? `&status=${status}` : "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <SlateHeader
        sport="nfl"
        season={schedule.season}
        slates={slates}
        slate={slate}
        record={record}
        counter={weekCounter(games)}
        query={statusQuery}
        statusQuery={statusQuery}
      >
        <StatusFilter sport="nfl" active={status} slateQuery={slate ? slateQuery(slate) : ""} />
      </SlateHeader>

      <div className="mt-8 space-y-8">
        <Disagreements games={games} sport="nfl" />
        <SlateGames
          games={games}
          sport="nfl"
          filtered={status !== "all"}
          postseason={slate?.phase === "postseason"}
        />
      </div>
    </div>
  );
}

async function CfbSlate({
  requested,
  conf,
  top25: wantTop25,
  status,
}: {
  requested: { week?: string; round?: string };
  conf?: string;
  top25: boolean;
  status: StatusFilterValue;
}) {
  const recordPromise = fetchRecordSafely("CFB");
  let slate: Slate | undefined;
  let slates: Slate[];
  // Per-slate fetch: the CFB slate is 60+ games a week, never the whole season.
  let games: GameSummary[];
  try {
    slates = await getSlates(2026, "CFB");
    slate = resolveSlate(slates, requested);
    games = slate
      ? await getGames(
          slate.week,
          2026,
          "CFB",
          status,
          slate.phase === "postseason" ? slate.key : undefined
        )
      : [];
  } catch (e) {
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }
  const record = await recordPromise;

  // Conference and Top 25 chips apply to regular weeks and bowls only.
  const showChips = !slate || slate.phase === "regular" || slate.key === "bowls";
  const conferences = showChips
    ? [
        ...new Set(
          games
            .flatMap((g) => [g.home.conference, g.away.conference])
            .filter((c): c is string => !!c)
        ),
      ].sort()
    : [];
  const activeConf = conf && conferences.includes(conf) ? conf : null;
  const top25 = showChips && wantTop25;

  const filtered = games.filter((g) => {
    if (activeConf && g.home.conference !== activeConf && g.away.conference !== activeConf)
      return false;
    if (top25 && g.home.rank == null && g.away.rank == null) return false;
    return true;
  });
  const confQuery = `${activeConf ? `&conf=${encodeURIComponent(activeConf)}` : ""}${top25 ? "&top25=1" : ""}`;
  const statusQuery = status !== "all" ? `&status=${status}` : "";
  const current = slate ? slateQuery(slate) : "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <SlateHeader
        sport="cfb"
        season={2026}
        slates={slates}
        slate={slate}
        record={record}
        counter={weekCounter(filtered)}
        query={`${confQuery}${statusQuery}`}
        statusQuery={statusQuery}
      >
        {showChips && (
          <FilterChips
            conferences={conferences}
            activeConf={activeConf}
            top25={top25}
            slateQuery={current}
            query={statusQuery}
          />
        )}
        <StatusFilter sport="cfb" active={status} slateQuery={current} query={confQuery} />
      </SlateHeader>

      <div className="mt-8 space-y-8">
        <Disagreements games={games} sport="cfb" />
        <SlateGames
          games={filtered}
          sport="cfb"
          filtered={!!activeConf || top25 || status !== "all"}
          postseason={slate?.phase === "postseason"}
        />
      </div>
    </div>
  );
}

export default async function SlatePage({ params, searchParams }: Props) {
  const { sport } = await params;
  if (!isSportSlug(sport)) notFound();

  const sp = await searchParams;
  const requested = { week: one(sp.week), round: one(sp.round) };
  const status = validStatus(one(sp.status));

  if (sport === "cfb") {
    return (
      <CfbSlate
        requested={requested}
        conf={one(sp.conf)}
        top25={one(sp.top25) === "1"}
        status={status}
      />
    );
  }
  return <NflSlate requested={requested} status={status} />;
}
