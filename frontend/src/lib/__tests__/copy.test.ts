/** PS-F11: no new visitor-visible postseason copy carries an en or em dash,
 *  as a literal character or as an HTML entity. */

import fs from "fs";
import path from "path";
import React from "react";
import { render } from "@testing-library/react";
import HowItWorksPage from "@/app/how-it-works/page";
import { buildOgContent } from "../og";
import { backLink, matchupTitle, occasionLabel } from "../matchup";
import { REGULAR_OCCASION } from "../occasion";
import type { MatchupDetail, Occasion } from "../types";

const DASHES = new RegExp(`${String.fromCharCode(0x2013)}|${String.fromCharCode(0x2014)}|&mdash;|&ndash;`);

jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
  MockLink.displayName = "MockLink";
  return MockLink;
});

const SRC = path.join(__dirname, "..", "..");

// Files that render the new postseason copy. Comments are stripped: only what
// a visitor can see matters.
const FILES = [
  "components/GameCard.tsx",
  "components/MatchupHero.tsx",
  "components/Disagreements.tsx",
  "app/[sport]/matchup/[gameId]/page.tsx",
  "app/[sport]/matchup/[gameId]/opengraph-image.tsx",
  "app/[sport]/page.tsx",
  "app/how-it-works/page.tsx",
  "lib/matchup.ts",
  "lib/og.ts",
  "lib/format.ts",
];

function withoutComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
}

function matchup(occasion: Partial<Occasion>, week: number, neutral: boolean): MatchupDetail {
  return {
    game_id: "g",
    season: 2026,
    week,
    kickoff: null,
    venue: { name: null, city: null, is_dome: null, is_neutral_site: neutral },
    is_primetime: false,
    is_divisional: false,
    home: { abbr: "DET", name: "Lions", record: "0-0", logo_url: null, win_prob: 0.5 },
    away: { abbr: "BUF", name: "Bills", record: "0-0", logo_url: null, win_prob: 0.5 },
    odds: null,
    weather: null,
    factors: [],
    narrative: null,
    model_version: null,
    predicted_at: null,
    prediction_status: "ready",
    sport: "NFL",
    home_score: null,
    away_score: null,
    prediction_correct: null,
    ...REGULAR_OCCASION,
    ...occasion,
  };
}

const SAMPLES: MatchupDetail[] = [
  matchup({}, 5, false),
  matchup({ season_type: "postseason", round: "wild_card", event_name: "AFC Wild Card" }, 19, false),
  matchup({ season_type: "postseason", round: "super_bowl", event_name: "Super Bowl LXI" }, 22, true),
  matchup({ season_type: "postseason", round: "bowl", event_name: "Duke's Mayo Bowl" }, 17, true),
  matchup({ season_type: "postseason", round: "cfp_championship", event_name: "CFP National Championship" }, 17, true),
  matchup({ round: "conf_championship", event_name: "SEC Championship" }, 14, true),
];

describe("PS-F11: postseason copy has no en or em dashes", () => {
  test.each(FILES)("PS-F11: %s", (file) => {
    const src = fs.readFileSync(path.join(SRC, file), "utf8");
    expect(withoutComments(src)).not.toMatch(DASHES);
  });

  test("PS-F11: matchup titles, back links and OG footers", () => {
    for (const m of SAMPLES) {
      const og = buildOgContent(m);
      const strings = [
        matchupTitle(m),
        occasionLabel(m),
        backLink(m, "nfl").label,
        `${og.occasion} ${og.season}`,
        og.separator,
      ];
      for (const s of strings) expect(s).not.toMatch(DASHES);
    }
  });

  test("PS-F11: How It Works carries the postseason paragraph without dashes", () => {
    const { container } = render(React.createElement(HowItWorksPage));
    const text = container.textContent ?? "";
    expect(text).toMatch(/neutral sites/i);
    expect(text).toMatch(/opt-outs and coaching changes/i);
    expect(text).toMatch(/market line is shown beside every pick/i);
    expect(container.innerHTML).not.toMatch(DASHES);
  });
});
