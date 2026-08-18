/** GameCard rendering tests: teams, win probabilities, badges, and links. */

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
    market_home_prob: null,
    home_score: null,
    away_score: null,
    prediction_correct: null,
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
    const tbdBadge = container.querySelector('span[class*="border-dashed"]');
    expect(tbdBadge).toBeInTheDocument();
    expect(tbdBadge?.textContent).toMatch(/TBD/);
  });

  test("renders kickoff time when available", () => {
    render(<GameCard game={baseGame} />);

    const gamecard = screen.getByRole("link");
    expect(gamecard.textContent).toMatch(/\d{1,2}:\d{2}\s(AM|PM)\sET/);
  });

  test("displays win probability bar when prediction available", () => {
    const gameWithProb = {
      ...baseGame,
      home_win_prob: 0.6,
    };

    const { container } = render(<GameCard game={gameWithProb} />);

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
      market_home_prob: null,
      home_score: null,
      away_score: null,
      prediction_correct: null,
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

    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  const finalGame = (correct: boolean | null) => ({
    ...baseGame,
    home_score: 27,
    away_score: 24,
    home_win_prob: correct === false ? 0.38 : 0.62,
    prediction_correct: correct,
  });

  test("final game shows both scores", () => {
    render(<GameCard game={finalGame(true)} />);
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
  });

  test("correct prediction shows a called-it badge", () => {
    render(<GameCard game={finalGame(true)} />);
    expect(screen.getByText(/called it/i)).toBeInTheDocument();
  });

  test("incorrect prediction shows a missed badge", () => {
    render(<GameCard game={finalGame(false)} />);
    expect(screen.getByText(/missed/i)).toBeInTheDocument();
  });

  test("final game with no prediction shows score but no verdict", () => {
    render(<GameCard game={{ ...finalGame(null), home_win_prob: undefined }} />);
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.queryByText(/called it|missed/i)).not.toBeInTheDocument();
  });

  test("final game with has_prediction false does not show 'Prediction pending'", () => {
    render(
      <GameCard
        game={{ ...finalGame(null), home_win_prob: undefined, has_prediction: false }}
      />
    );
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.queryByText(/prediction pending/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/called it|missed/i)).not.toBeInTheDocument();
  });

  test("verdict is not conveyed by color alone", () => {
    render(<GameCard game={finalGame(true)} />);
    // A screen reader user must get the verdict as text.
    expect(screen.getByText(/called it/i)).toBeInTheDocument();
  });
});
