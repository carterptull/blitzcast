import type { MetadataRoute } from "next";
import { unstable_cache } from "next/cache";
import { getSchedule } from "@/lib/api";

// Mirrors the canonical-domain resolution in layout.tsx's metadataBase.
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ??
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");

export const revalidate = 3600;

const SPORTS = [
  { slug: "nfl", api: "NFL" as const },
  { slug: "cfb", api: "CFB" as const },
] as const;

// getSchedule() revalidates every 30s via api.ts, and unstable_cache stretches
// that to one fetch per sport per hour, matching the revalidate export.
const getCachedSchedule = unstable_cache(
  async (season: number, sport: "NFL" | "CFB") => getSchedule(season, sport, "all"),
  ["sitemap-schedule"],
  { revalidate: 3600 }
);

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: siteUrl, changeFrequency: "daily", priority: 1 },
    { url: `${siteUrl}/how-it-works`, changeFrequency: "monthly", priority: 0.5 },
  ];

  for (const { slug, api } of SPORTS) {
    entries.push({ url: `${siteUrl}/${slug}`, changeFrequency: "hourly", priority: 0.9 });

    // Bounded to the current season only (2026), never historical seasons —
    // the payload stays flat regardless of how many past seasons pile up.
    try {
      const schedule = await getCachedSchedule(2026, api);
      for (const week of schedule.weeks) {
        for (const game of week.games) {
          entries.push({
            url: `${siteUrl}/${slug}/matchup/${encodeURIComponent(game.game_id)}`,
            lastModified: game.kickoff ? new Date(game.kickoff) : undefined,
            changeFrequency:
              game.home_score !== null && game.away_score !== null ? "yearly" : "daily",
            priority: 0.6,
          });
        }
      }
    } catch {
      // Backend unreachable when the sitemap regenerates — ship the static
      // entries rather than failing sitemap.xml outright; the next
      // revalidation will pick matchups back up once the backend recovers.
    }
  }

  return entries;
}
