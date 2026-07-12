import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError, getMatchup, NotFoundError } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { apiSport, isSportSlug } from "@/lib/sport";
import type { MatchupDetail } from "@/lib/types";
import BackendDown from "@/components/BackendDown";
import MatchupHero from "@/components/MatchupHero";
import ReasoningPanel from "@/components/ReasoningPanel";
import StatTicker from "@/components/StatTicker";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ sport: string; gameId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { gameId } = await params;
  try {
    const m = await getMatchup(gameId);
    const league = m.sport === "CFB" ? "college football" : "NFL";
    const title = `${m.away.abbr} @ ${m.home.abbr} — Week ${m.week}`;
    const favored = m.home.win_prob !== null && m.home.win_prob >= 0.5 ? m.home : m.away;
    const description =
      favored.win_prob !== null
        ? `Blitzcast gives the ${favored.name} a ${fmtPct(favored.win_prob)} chance in ${m.away.name} at ${m.home.name}, Week ${m.week} of the ${m.season} ${league} season.`
        : `${m.away.name} at ${m.home.name}, Week ${m.week} of the ${m.season} ${league} season — prediction coming after the weekly data refresh.`;
    return {
      title,
      description,
      openGraph: { title: `${title} · Blitzcast`, description, type: "website" },
    };
  } catch {
    return { title: "Matchup" };
  }
}

export default async function MatchupPage({ params }: Props) {
  const { sport, gameId } = await params;
  if (!isSportSlug(sport)) notFound();

  let matchup: MatchupDetail;
  try {
    matchup = await getMatchup(gameId);
  } catch (e) {
    if (e instanceof NotFoundError) notFound();
    if (e instanceof ApiUnreachableError) return <BackendDown />;
    throw e;
  }

  // A game only lives under its own sport's path.
  if (matchup.sport && matchup.sport !== apiSport(sport)) notFound();

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Link
        href={`/${sport}?week=${matchup.week}`}
        className="mb-4 inline-flex items-center gap-2 rounded-sm font-mono text-[11px] uppercase tracking-[0.18em] text-ink-soft transition-colors hover:text-gold-text"
      >
        <span aria-hidden="true">←</span> Week {matchup.week} slate
      </Link>

      <div className="space-y-6">
        <MatchupHero matchup={matchup} />
        <StatTicker matchup={matchup} />
        <ReasoningPanel matchup={matchup} />
      </div>
    </div>
  );
}
