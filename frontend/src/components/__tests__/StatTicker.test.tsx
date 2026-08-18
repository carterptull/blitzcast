/** StatTicker rendering tests: market/venue cells plus the "Final" result
 *  cell added for finished games. */

import React from "react";
import { render, screen } from "@testing-library/react";
import StatTicker from "../StatTicker";
import type { MatchupDetail } from "@/lib/types";

const baseMatchup: MatchupDetail = {
  game_id: "2026_01_KC_SF",
  season: 2026,
  week: 1,
  kickoff: "2026-09-10T20:20:00Z",
  venue: { name: "Levi's Stadium", city: "Santa Clara", is_dome: false },
  is_primetime: false,
  is_divisional: false,
  home: {
    abbr: "SF",
    name: "49ers",
    record: "0-0",
    logo_url: null,
    win_prob: 0.62,
  },
  away: {
    abbr: "KC",
    name: "Chiefs",
    record: "0-0",
    logo_url: null,
    win_prob: 0.38,
  },
  odds: null,
  weather: null,
  factors: [],
  narrative: null,
  model_version: "0.1.0",
  predicted_at: "2026-09-08T12:00:00Z",
  prediction_status: "ready",
  sport: "NFL",
  home_score: null,
  away_score: null,
  prediction_correct: null,
};

describe("StatTicker", () => {
  test("does not render a Final cell before the game is over", () => {
    render(<StatTicker matchup={baseMatchup} />);
    expect(screen.queryByText("Final")).not.toBeInTheDocument();
  });

  test("renders a Final cell with both scores once the game is over", () => {
    const finalMatchup: MatchupDetail = {
      ...baseMatchup,
      home_score: 27,
      away_score: 24,
      prediction_correct: true,
    };
    render(<StatTicker matchup={finalMatchup} />);
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.getByText("KC 24 / SF 27")).toBeInTheDocument();
  });

  test("uses LAR display abbreviation for the Rams in the Final cell", () => {
    const finalMatchup: MatchupDetail = {
      ...baseMatchup,
      home: { ...baseMatchup.home, abbr: "LA" },
      home_score: 20,
      away_score: 17,
      prediction_correct: false,
    };
    render(<StatTicker matchup={finalMatchup} />);
    expect(screen.getByText("KC 17 / LAR 20")).toBeInTheDocument();
  });

  test("does not add a Final cell when only one score is present", () => {
    const partial: MatchupDetail = {
      ...baseMatchup,
      home_score: 27,
      away_score: null,
    };
    render(<StatTicker matchup={partial} />);
    expect(screen.queryByText("Final")).not.toBeInTheDocument();
  });
});
