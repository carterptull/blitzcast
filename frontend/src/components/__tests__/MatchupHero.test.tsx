/** MatchupHero rendering tests: pre-game state plus the final-state score,
 *  "Final" pill, and verdict band added for finished games. */

import React from "react";
import { render, screen } from "@testing-library/react";
import MatchupHero from "../MatchupHero";
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
  narrative: "Some narrative text.",
  model_version: "0.1.0",
  predicted_at: "2026-09-08T12:00:00Z",
  prediction_status: "ready",
  sport: "NFL",
  home_score: null,
  away_score: null,
  prediction_correct: null,
};

const finalMatchup = (correct: boolean | null): MatchupDetail => ({
  ...baseMatchup,
  home_score: 27,
  away_score: 24,
  prediction_correct: correct,
});

describe("MatchupHero", () => {
  test("pre-game matchup shows win probabilities, not scores", () => {
    render(<MatchupHero matchup={baseMatchup} />);
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("38%")).toBeInTheDocument();
    expect(screen.queryByText("Final")).not.toBeInTheDocument();
  });

  test("final matchup renders both scores", () => {
    render(<MatchupHero matchup={finalMatchup(true)} />);
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
  });

  test("final matchup shows a Final pill in the meta line", () => {
    const { container } = render(<MatchupHero matchup={finalMatchup(true)} />);
    // The meta-line pill reuses the shared Badge component styling; the team
    // columns also say "Final" as a caption, so scope to the badge markup.
    const pill = container.querySelector('span[class*="border-gold-turf"]');
    expect(pill?.textContent).toBe("Final");
  });

  test("final matchup labels the score columns Final instead of Win probability", () => {
    render(<MatchupHero matchup={finalMatchup(true)} />);
    expect(screen.queryByText("Win probability")).not.toBeInTheDocument();
  });

  test("correct prediction shows a hit verdict in the band", () => {
    render(<MatchupHero matchup={finalMatchup(true)} />);
    expect(screen.getByText(/model called it/i)).toBeInTheDocument();
  });

  test("incorrect prediction shows a miss verdict in the band", () => {
    render(<MatchupHero matchup={finalMatchup(false)} />);
    expect(screen.getByText(/model missed/i)).toBeInTheDocument();
  });

  test("final matchup with no graded prediction shows neither verdict phrase", () => {
    render(<MatchupHero matchup={finalMatchup(null)} />);
    expect(screen.queryByText(/model called it/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/model missed/i)).not.toBeInTheDocument();
    // The score is still shown even without a graded call.
    expect(screen.getByText("27")).toBeInTheDocument();
  });

  test("verdict is conveyed by text, not color alone", () => {
    render(<MatchupHero matchup={finalMatchup(false)} />);
    // A screen reader user must get the verdict as text content.
    expect(screen.getByText("Model missed")).toBeInTheDocument();
  });
});
