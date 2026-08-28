import { ImageResponse } from "next/og";

export const alt = "Blitzcast: NFL & college football win probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Site-wide default OG card, served for any route that doesn't define its
// own opengraph-image (matchup pages override this with a per-game card).
// Same fixed dark-turf palette as the matchup fallback — see that file's
// comment for why the values are pinned rather than pulled from CSS.
const STRIPE_A = "#0f2a1d";
const STRIPE_B = "#18402c";
const GOLD_TURF = "#f0c464";
const CHALK = "#eef4ec";
const CHALK_SOFT = "rgba(238, 244, 236, 0.7)";

const STRIPE_WIDTH = 100;
const STRIPE_COUNT = size.width / STRIPE_WIDTH;

export default function Image() {
  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", position: "relative", backgroundColor: STRIPE_A }}>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "row" }}>
          {Array.from({ length: STRIPE_COUNT }).map((_, i) => (
            <div
              key={`stripe-${i}`}
              style={{ width: STRIPE_WIDTH, height: "100%", backgroundColor: i % 2 === 0 ? STRIPE_A : STRIPE_B }}
            />
          ))}
        </div>
        <div
          style={{
            position: "relative",
            display: "flex",
            flexDirection: "column",
            width: "100%",
            height: "100%",
            alignItems: "center",
            justifyContent: "center",
            gap: 24,
          }}
        >
          <div style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 20 }}>
            <div style={{ display: "flex", width: 36, height: 22, borderRadius: 999, backgroundColor: GOLD_TURF }} />
            <div style={{ display: "flex", fontSize: 64, fontWeight: 700, letterSpacing: 4, textTransform: "uppercase", color: CHALK }}>
              Blitzcast
            </div>
          </div>
          <div style={{ display: "flex", fontSize: 28, letterSpacing: 2, color: CHALK_SOFT }}>
            Every matchup, called before kickoff
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}
