/** Disagreements rendering tests: largest model-vs-market gaps, informational
 *  framing only, no market-data games excluded. */

import React from "react";
import { render, screen } from "@testing-library/react";
import Disagreements from "../Disagreements";
import type { GameSummary } from "@/lib/types";

// Mock Next.js Link component to avoid routing issues in tests
jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

function game(overrides: Partial<GameSummary> = {}): GameSummary {
  return {
    game_id: "2026_01_AWY_HME",
    kickoff: "2026-09-10T20:20:00Z",
    home: { abbr: "HME", name: "Home Team" },
    away: { abbr: "AWY", name: "Away Team" },
    is_primetime: false,
    status: "scheduled",
    has_prediction: true,
    home_win_prob: 0.6,
    market_home_prob: 0.5,
    home_score: null,
    away_score: null,
    prediction_correct: null,
    ...overrides,
  };
}

describe("Disagreements", () => {
  test("renders nothing when no games have market data", () => {
    const games = [
      game({ game_id: "g1", market_home_prob: null }),
      game({ game_id: "g2", home_win_prob: null, market_home_prob: 0.4 }),
    ];
    const { container } = render(<Disagreements games={games} sport="nfl" />);
    expect(container).toBeEmptyDOMElement();
  });

  test("excludes games with no market data from the list", () => {
    const games = [
      game({ game_id: "g1", home: { abbr: "AAA", name: "Team AAA" }, market_home_prob: null }),
      game({ game_id: "g2", home: { abbr: "BBB", name: "Team BBB" }, home_win_prob: 0.7, market_home_prob: 0.5 }),
    ];
    render(<Disagreements games={games} sport="nfl" />);
    expect(screen.queryByText(/AAA/)).not.toBeInTheDocument();
    expect(screen.getByText(/BBB/)).toBeInTheDocument();
  });

  test("orders games by the largest absolute gap first", () => {
    const games = [
      game({ game_id: "g1", home: { abbr: "SMALL", name: "Small Gap" }, home_win_prob: 0.55, market_home_prob: 0.5 }),
      game({ game_id: "g2", home: { abbr: "BIG", name: "Big Gap" }, home_win_prob: 0.8, market_home_prob: 0.4 }),
    ];
    render(<Disagreements games={games} sport="nfl" />);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveTextContent(/BIG/);
    expect(links[1]).toHaveTextContent(/SMALL/);
  });

  test("shows at most three games", () => {
    const games = Array.from({ length: 6 }, (_, i) =>
      game({
        game_id: `g${i}`,
        home: { abbr: `T${i}`, name: `Team ${i}` },
        home_win_prob: 0.5 + i * 0.05,
        market_home_prob: 0.5,
      })
    );
    render(<Disagreements games={games} sport="nfl" />);
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  test("copy avoids betting-action language", () => {
    const games = [
      game({ home_win_prob: 0.75, market_home_prob: 0.4 }),
    ];
    render(<Disagreements games={games} sport="nfl" />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bbet\b|\bwager\b|\bstake\b|\bedge\b|\bcover\b/i);
  });

  test("links to the matchup detail page under the given sport", () => {
    const games = [game({ game_id: "2026_01_XYZ", home_win_prob: 0.75, market_home_prob: 0.4 })];
    render(<Disagreements games={games} sport="cfb" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/cfb/matchup/2026_01_XYZ");
  });
});
