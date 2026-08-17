/** ReasoningPanel rendering tests: pending/ready narrative states plus the
 *  final-state verdict sentence and the backtest-reconstruction label. */

import React from "react";
import { render, screen } from "@testing-library/react";
import ReasoningPanel from "../ReasoningPanel";
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
  narrative: "The model leans on home-field edge and a healthier secondary.",
  model_version: "0.1.0",
  predicted_at: "2026-09-08T12:00:00Z",
  prediction_status: "ready",
  sport: "NFL",
  home_score: null,
  away_score: null,
  prediction_correct: null,
};

describe("ReasoningPanel", () => {
  test("pending prediction shows the waiting copy, not the narrative", () => {
    render(<ReasoningPanel matchup={{ ...baseMatchup, prediction_status: "pending" }} />);
    expect(screen.getByText(/hasn't weighed in on this one yet/i)).toBeInTheDocument();
  });

  test("pre-game ready matchup shows the narrative with no verdict sentence", () => {
    render(<ReasoningPanel matchup={baseMatchup} />);
    expect(
      screen.getByText("The model leans on home-field edge and a healthier secondary.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/the call landed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/the call missed/i)).not.toBeInTheDocument();
  });

  test("final matchup with a correct call states the pick landed", () => {
    const m: MatchupDetail = {
      ...baseMatchup,
      home_score: 27,
      away_score: 24,
      prediction_correct: true,
    };
    render(<ReasoningPanel matchup={m} />);
    expect(screen.getByText(/the model favored sf to win, and the call landed/i)).toBeInTheDocument();
  });

  test("final matchup with an incorrect call states the pick missed", () => {
    const m: MatchupDetail = {
      ...baseMatchup,
      home_score: 17,
      away_score: 24,
      prediction_correct: false,
    };
    render(<ReasoningPanel matchup={m} />);
    expect(screen.getByText(/the model favored sf to win, and the call missed/i)).toBeInTheDocument();
  });

  test("final matchup with no graded prediction shows no verdict sentence", () => {
    const m: MatchupDetail = {
      ...baseMatchup,
      home_score: 17,
      away_score: 24,
      prediction_correct: null,
    };
    render(<ReasoningPanel matchup={m} />);
    expect(screen.queryByText(/the call landed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/the call missed/i)).not.toBeInTheDocument();
  });

  test("backtest-reconstructed predictions are labeled as such", () => {
    render(<ReasoningPanel matchup={{ ...baseMatchup, model_version: "backtest-2024" }} />);
    expect(screen.getByText(/reconstructed from a backtest/i)).toBeInTheDocument();
  });

  test("live predictions do not show the reconstructed label", () => {
    render(<ReasoningPanel matchup={{ ...baseMatchup, model_version: "0.1.0" }} />);
    expect(screen.queryByText(/reconstructed from a backtest/i)).not.toBeInTheDocument();
  });

  test("a matchup with no model version does not show the reconstructed label", () => {
    render(<ReasoningPanel matchup={{ ...baseMatchup, model_version: null }} />);
    expect(screen.queryByText(/reconstructed from a backtest/i)).not.toBeInTheDocument();
  });
});
