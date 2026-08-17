/**
 * GameCard Component Tests
 *
 * Tests the game card component for correct rendering of:
 * - Team names and abbreviations
 * - Win probabilities
 * - Primetime indicators
 * - Pending prediction states
 * - Links to matchup pages
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import GameCard from "../GameCard";
import type { GameSummary } from "@/lib/types";

// Mock Next.js Link component to avoid routing issues in tests
jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

describe("GameCard", () => {
  const baseGame: GameSummary = {
    game_id: "2026_01_KC_SF",
    kickoff: "2026-09-10T20:20:00Z",
    home: {
      abbr: "SF",
      name: "San Francisco 49ers",
      conference: "NFC",
    },
    away: {
      abbr: "KC",
      name: "Kansas City Chiefs",
      conference: "AFC",
    },
    is_primetime: false,
    status: "scheduled",
    has_prediction: true,
  };

  test("renders team abbreviations", () => {
    render(<GameCard game={baseGame} />);

    expect(screen.getByText("SF")).toBeInTheDocument();
    expect(screen.getByText("KC")).toBeInTheDocument();
  });

  test("renders team full names", () => {
    render(<GameCard game={baseGame} />);

    expect(screen.getByText("San Francisco 49ers")).toBeInTheDocument();
    expect(screen.getByText("Kansas City Chiefs")).toBeInTheDocument();
  });

  test("renders win probability when available", () => {
    const gameWithProb = {
      ...baseGame,
      home_win_prob: 0.62,
    };

    render(<GameCard game={gameWithProb} />);

    // 62% and 38% (1 - 0.62) should both be displayed
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("38%")).toBeInTheDocument();
  });

  test("shows pending prediction badge when no prediction", () => {
    const gameNoPrediction = {
      ...baseGame,
      has_prediction: false,
    };

    render(<GameCard game={gameNoPrediction} />);
    expect(screen.getByText("Prediction pending")).toBeInTheDocument();
  });

  test("renders primetime indicator when is_primetime is true", () => {
    const primetimeGame = {
      ...baseGame,
      is_primetime: true,
    };

    render(<GameCard game={primetimeGame} />);
    expect(screen.getByText("Prime time")).toBeInTheDocument();
  });

  test("does not render primetime indicator when is_primetime is false", () => {
    render(<GameCard game={baseGame} />);
    expect(screen.queryByText("Prime time")).not.toBeInTheDocument();
  });

  test("links to correct matchup page", () => {
    render(<GameCard game={baseGame} />);

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/nfl/matchup/2026_01_KC_SF");
  });

  test("links to CFB matchup when sport is cfb", () => {
    render(<GameCard game={baseGame} sport="cfb" />);

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/cfb/matchup/2026_01_KC_SF");
  });

  test("renders TBD badge when kickoff is null", () => {
    const tbdGame = {
      ...baseGame,
      kickoff: null,
    };

    const { container } = render(<GameCard game={tbdGame} />);
    // TbdBadge component should be present (renders "Time TBD" text)
    const tbdBadge = container.querySelector('span[class*="border-dashed"]');
    expect(tbdBadge).toBeInTheDocument();
    expect(tbdBadge?.textContent).toMatch(/TBD/);
  });

  test("renders kickoff time when available", () => {
    render(<GameCard game={baseGame} />);

    // Should have time in HH:MM AM/PM ET format (from fmtKickoffTime)
    const gamecard = screen.getByRole("link");
    expect(gamecard.textContent).toMatch(/\d{1,2}:\d{2}\s(AM|PM)\sET/);
  });

  test("displays win probability bar when prediction available", () => {
    const gameWithProb = {
      ...baseGame,
      home_win_prob: 0.6,
    };

    const { container } = render(<GameCard game={gameWithProb} />);

    // Should have a progress bar element (the one with style transforms)
    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar).toBeInTheDocument();
  });

  test("shows hatched pattern when no prediction", () => {
    const gameNoPrediction = {
      ...baseGame,
      has_prediction: false,
      home_win_prob: undefined,
    };

    const { container } = render(<GameCard game={gameNoPrediction} />);

    // Should have hatch class instead of progress bar
    const hatch = container.querySelector(".hatch");
    expect(hatch).toBeInTheDocument();
  });

  test("handles missing optional fields gracefully", () => {
    const minimalGame = {
      game_id: "2026_01_TEST_GAME",
      kickoff: null,
      home: { abbr: "TST", name: "Test Home" },
      away: { abbr: "AWY", name: "Test Away" },
      is_primetime: false,
      status: "scheduled",
      has_prediction: true,
    };

    render(<GameCard game={minimalGame} />);

    expect(screen.getByText("Test Home")).toBeInTheDocument();
    expect(screen.getByText("Test Away")).toBeInTheDocument();
    expect(screen.getByText(/Time TBD|TBD/)).toBeInTheDocument();
  });

  test("correctly calculates away win probability as 1 - home_win_prob", () => {
    const gameWithProb = {
      ...baseGame,
      home_win_prob: 0.75,
    };

    render(<GameCard game={gameWithProb} />);

    // 75% home win prob = 25% away win prob
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
});
