/** Week counter logic: switches from "X/Y predicted" to "X/Y correct" only
 *  when every displayed game is final, grading against `prediction_correct`.
 *  A mixed week (any non-final game) always keeps "predicted". */

import { weekCounter } from "../page";
import type { GameSummary } from "@/lib/types";

function game(overrides: Partial<GameSummary> = {}): GameSummary {
  return {
    game_id: "2026_01_KC_SF",
    kickoff: "2026-09-10T20:20:00Z",
    home: { abbr: "SF", name: "San Francisco 49ers", conference: "NFC" },
    away: { abbr: "KC", name: "Kansas City Chiefs", conference: "AFC" },
    is_primetime: false,
    status: "scheduled",
    has_prediction: true,
    market_home_prob: null,
    home_score: null,
    away_score: null,
    prediction_correct: null,
    ...overrides,
  };
}

const upcoming = (hasPrediction: boolean) => game({ has_prediction: hasPrediction });
const finalGame = (correct: boolean | null) =>
  game({ home_score: 27, away_score: 24, prediction_correct: correct });

describe("weekCounter", () => {
  test("mixed week (some final, some not) reads 'predicted', counting predictions over all games", () => {
    const games = [upcoming(true), upcoming(true), upcoming(false), finalGame(true)];
    expect(weekCounter(games)).toEqual({ count: 3, total: 4, label: "predicted" });
  });

  test("all-final week reads 'correct', counting graded verdicts", () => {
    const games = [finalGame(true), finalGame(true), finalGame(false)];
    expect(weekCounter(games)).toEqual({ count: 2, total: 3, label: "correct" });
  });

  test("a final tie/no-pick game (prediction_correct: null) counts toward the total but not toward correct", () => {
    const games = [finalGame(true), finalGame(false), finalGame(null)];
    expect(weekCounter(games)).toEqual({ count: 1, total: 3, label: "correct" });
  });

  test("a single non-final game keeps 'predicted' wording even if every other game is final", () => {
    const games = [finalGame(true), finalGame(true), upcoming(true)];
    expect(weekCounter(games)).toEqual({ count: 3, total: 3, label: "predicted" });
  });

  test("an empty week stays 'predicted' rather than vacuously 'correct'", () => {
    expect(weekCounter([])).toEqual({ count: 0, total: 0, label: "predicted" });
  });

  test("all-final week with no correct calls reports zero correct, not zero total", () => {
    const games = [finalGame(false), finalGame(false)];
    expect(weekCounter(games)).toEqual({ count: 0, total: 2, label: "correct" });
  });
});
