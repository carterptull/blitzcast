import { ImageResponse } from "next/og";
import { getMatchup } from "@/lib/api";
import { buildOgContent } from "@/lib/og";
import { primaryColor } from "@/lib/teams";
import type { MatchupDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export const alt = "Blitzcast matchup prediction";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Fixed dark-turf palette, mirrored from globals.css's dark theme. OG images
// render outside the site's light/dark toggle (and outside Tailwind/CSS
// custom properties, which satori can't resolve), so the values are pinned
// here rather than imported.
const STRIPE_A = "#0f2a1d";
const STRIPE_B = "#18402c";
const GOLD_TURF = "#f0c464";
const CHALK = "#eef4ec";
const CHALK_SOFT = "rgba(238, 244, 236, 0.7)";
const VERDICT_HIT_TURF = "#8fe0c4";
const VERDICT_MISS_TURF = "#eeb3b3";
const NEUTRAL_PRIMARY = "#4f6459";

const STRIPE_WIDTH = 100;
const STRIPE_COUNT = size.width / STRIPE_WIDTH;

interface Props {
  params: Promise<{ sport: string; gameId: string }>;
}

function TurfBackdrop() {
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "row" }}>
      {Array.from({ length: STRIPE_COUNT }).map((_, i) => (
        <div
          key={`stripe-${i}`}
          style={{ width: STRIPE_WIDTH, height: "100%", backgroundColor: i % 2 === 0 ? STRIPE_A : STRIPE_B }}
        />
      ))}
    </div>
  );
}

function Brand() {
  return (
    <div style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 16 }}>
      <div style={{ display: "flex", width: 26, height: 16, borderRadius: 999, backgroundColor: GOLD_TURF }} />
      <div style={{ display: "flex", fontSize: 34, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase", color: CHALK }}>
        Blitzcast
      </div>
    </div>
  );
}

function TeamBlock({
  abbr,
  value,
  sub,
  highlight,
}: {
  abbr: string;
  value: string;
  sub: string;
  highlight: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, width: 340 }}>
      <div style={{ display: "flex", fontSize: 54, fontWeight: 700, letterSpacing: 2, color: CHALK }}>{abbr}</div>
      <div
        style={{
          display: "flex",
          fontSize: 88,
          fontWeight: 700,
          color: highlight ? GOLD_TURF : CHALK,
        }}
      >
        {value}
      </div>
      <div style={{ display: "flex", fontSize: 18, textTransform: "uppercase", letterSpacing: 3, color: CHALK_SOFT }}>
        {sub}
      </div>
    </div>
  );
}

/** Static two-color split, no animation — mirrors WinProbabilitySplit's
 *  team-color fill without the client-side mount transition. */
function ProbabilityBar({ m, cfb }: { m: MatchupDetail; cfb: boolean }) {
  const awayProb = m.away.win_prob ?? 0.5;
  const homeProb = m.home.win_prob ?? 0.5;
  const sport = cfb ? "CFB" : "NFL";
  const awayColor = cfb ? primaryColor(sport, m.away.abbr, m.away.color) : primaryColor(sport, m.away.abbr);
  const homeColor = cfb ? primaryColor(sport, m.home.abbr, m.home.color) : primaryColor(sport, m.home.abbr);
  return (
    <div style={{ display: "flex", flexDirection: "row", width: 760, height: 14, borderRadius: 7, overflow: "hidden" }}>
      <div style={{ display: "flex", width: `${awayProb * 100}%`, height: "100%", backgroundColor: awayColor || NEUTRAL_PRIMARY }} />
      <div style={{ display: "flex", width: `${homeProb * 100}%`, height: "100%", backgroundColor: homeColor || NEUTRAL_PRIMARY }} />
    </div>
  );
}

function fallbackImage() {
  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", position: "relative", backgroundColor: STRIPE_A }}>
        <TurfBackdrop />
        <div
          style={{
            position: "relative",
            display: "flex",
            flexDirection: "column",
            width: "100%",
            height: "100%",
            alignItems: "center",
            justifyContent: "center",
            gap: 20,
          }}
        >
          <Brand />
          <div style={{ display: "flex", fontSize: 26, letterSpacing: 2, color: CHALK_SOFT }}>
            AI-powered NFL &amp; college football win probabilities
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}

export default async function Image({ params }: Props) {
  const { gameId } = await params;

  let m: MatchupDetail | null = null;
  try {
    m = await getMatchup(gameId);
  } catch {
    m = null;
  }

  if (!m) return fallbackImage();

  const c = buildOgContent(m);

  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", position: "relative", backgroundColor: STRIPE_A }}>
        <TurfBackdrop />
        <div
          style={{
            position: "relative",
            display: "flex",
            flexDirection: "column",
            width: "100%",
            height: "100%",
            padding: "56px 72px",
            justifyContent: "space-between",
          }}
        >
          <Brand />

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 }}>
            <div style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 48 }}>
              <TeamBlock abbr={c.away.abbr} value={c.away.value} sub={c.sub} highlight={c.away.highlight} />
              <div style={{ display: "flex", fontSize: 36, color: CHALK_SOFT }}>@</div>
              <TeamBlock abbr={c.home.abbr} value={c.home.value} sub={c.sub} highlight={c.home.highlight} />
            </div>

            {!c.final && c.hasProbs ? <ProbabilityBar m={m} cfb={c.cfb} /> : null}

            {c.verdictText ? (
              <div
                style={{
                  display: "flex",
                  fontSize: 20,
                  textTransform: "uppercase",
                  letterSpacing: 4,
                  color: c.verdictHit ? VERDICT_HIT_TURF : VERDICT_MISS_TURF,
                }}
              >
                {c.verdictText}
              </div>
            ) : c.pending ? (
              <div style={{ display: "flex", fontSize: 20, textTransform: "uppercase", letterSpacing: 4, color: CHALK_SOFT }}>
                Prediction pending
              </div>
            ) : null}
          </div>

          <div style={{ display: "flex", flexDirection: "row", justifyContent: "space-between", width: "100%" }}>
            <div style={{ display: "flex", fontSize: 20, textTransform: "uppercase", letterSpacing: 3, color: CHALK_SOFT }}>
              Week {c.week} &middot; {c.season}
            </div>
            <div style={{ display: "flex", fontSize: 20, textTransform: "uppercase", letterSpacing: 3, color: CHALK_SOFT }}>
              {c.league}
            </div>
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}
