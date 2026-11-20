/** Week counter logic: switches from "X/Y predicted" to "X/Y correct" only
 *  when every displayed game is final, grading against `prediction_correct`.
 *  A mixed week (any non-final game) always keeps "predicted". */

import React from "react";
import { render, screen } from "@testing-library/react";
import SlatePage, { weekCounter } from "../page";
import { getGames, getRecord, getSchedule, getSlates } from "@/lib/api";
import { REGULAR_OCCASION } from "@/lib/occasion";
import type { GameSummary, Slate } from "@/lib/types";

Element.prototype.scrollIntoView = jest.fn();

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  getSlates: jest.fn(),
  getGames: jest.fn(),
  getSchedule: jest.fn(),
  getRecord: jest.fn(),
}));

jest.mock("next/link", () => {
  const MockLink = ({
    children,
    href,
    "aria-current": ariaCurrent,
  }: {
    children: React.ReactNode;
    href: string;
    "aria-current"?: "true" | "false";
  }) => (
    <a href={href} aria-current={ariaCurrent}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

jest.mock("@/components/GameCard", () => {
  const MockCard = ({ game }: { game: { game_id: string } }) => (
    <div data-testid="card">{game.game_id}</div>
  );
  return MockCard;
});

jest.mock("@/components/Disagreements", () => {
  const MockDisagreements = () => null;
  return MockDisagreements;
});

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
    ...REGULAR_OCCASION,
    is_neutral_site: false,
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

const slate = (over: Partial<Slate>): Slate => ({
  key: "w1",
  phase: "regular",
  week: 1,
  round: null,
  label: null,
  group_label: "Wk",
  short_label: "1",
  game_count: 1,
  first_kickoff: null,
  next_kickoff: null,
  has_unscheduled: false,
  last_kickoff: null,
  ...over,
});

const regular = (n: number) => slate({ key: `w${n}`, week: n, short_label: String(n) });
const champ = slate({
  key: "w14",
  week: 14,
  round: "conf_championship",
  label: "Conference Championships",
  group_label: "Champ",
  short_label: "14",
});
// Bowls is the only live slate, so it is the default whatever today is.
const bowls = slate({
  key: "bowls",
  phase: "postseason",
  week: 17,
  round: "bowl",
  label: "Bowl Season",
  group_label: "Non-CFP",
  short_label: "Bowls",
  has_unscheduled: true,
});
const quarterfinals = slate({
  key: "cfp-quarterfinals",
  phase: "postseason",
  week: 17,
  round: "cfp_quarterfinal",
  label: "CFP Quarterfinals",
  group_label: "CFP",
  short_label: "QF",
});
const wildCard = slate({
  key: "wild-card",
  phase: "postseason",
  week: 19,
  round: "wild_card",
  label: "Wild Card",
  group_label: "Round",
  short_label: "WC",
  has_unscheduled: true,
});

const CFB_SLATES = [regular(13), champ, regular(15), bowls, quarterfinals];
const secGame = game({
  game_id: "cfb_1",
  home: { abbr: "UGA", name: "Georgia", conference: "SEC" },
  away: { abbr: "ALA", name: "Alabama", conference: "SEC" },
});

async function renderPage(sport: string, sp: { week?: string; round?: string } = {}) {
  const el = (await SlatePage({
    params: Promise.resolve({ sport }),
    searchParams: Promise.resolve(sp),
  })) as React.ReactElement;
  const tree = await (el.type as (p: unknown) => Promise<React.ReactElement>)(el.props);
  return render(tree);
}

const linkTo = (text: string) => screen.getByText(text).closest("a");

describe("SlatePage", () => {
  beforeEach(() => {
    jest.mocked(getRecord).mockRejectedValue(new Error("no record"));
    jest.mocked(getSlates).mockResolvedValue(CFB_SLATES);
    jest.mocked(getGames).mockResolvedValue([secGame]);
  });

  test("PS-F1 / PS-F4 / PS-F5 / PS-F6: CFB with postseason slates opens Postseason by default", async () => {
    await renderPage("cfb");
    expect(getSlates).toHaveBeenCalledWith(2026, "CFB");
    expect(getGames).toHaveBeenCalledWith(17, 2026, "CFB", "all", "bowls");
    expect(screen.getByText("2026 Postseason · Bowl Season")).toBeInTheDocument();
    expect(screen.getByText("Select a round")).toBeInTheDocument();
    expect(linkTo("Bowls")).toHaveAttribute("aria-current", "page");
    expect(linkTo("QF")).toHaveAttribute("href", "/cfb?round=cfp-quarterfinals");
    expect(screen.queryByText("Champ")).not.toBeInTheDocument();
    expect(linkTo("Postseason")).toHaveAttribute("aria-current", "true");
    expect(linkTo("Regular season")).toHaveAttribute("href", "/cfb?week=15");
  });

  test("PS-V2 / PS-F3: ?week=14 opens Week 14 even after postseason slates exist", async () => {
    await renderPage("cfb", { week: "14" });
    expect(getGames).toHaveBeenCalledWith(14, 2026, "CFB", "all", undefined);
    expect(screen.getByText("2026 Season · Conference Championships")).toBeInTheDocument();
    expect(screen.getByText("Select a week")).toBeInTheDocument();
    expect(linkTo("14")).toHaveAttribute("aria-current", "page");
    expect(linkTo("14")).toHaveTextContent("Champ14");
    expect(screen.queryByText("QF")).not.toBeInTheDocument();
    expect(linkTo("Regular season")).toHaveAttribute("aria-current", "true");
    expect(linkTo("Postseason")).toHaveAttribute("href", "/cfb?round=bowls");
    expect(screen.getByTestId("postseason-dot")).toBeInTheDocument();
  });

  test("PS-F10: conference and Top 25 chips show on regular weeks and bowls only", async () => {
    const { unmount } = await renderPage("cfb", { week: "14" });
    expect(screen.getByText("Top 25")).toBeInTheDocument();
    unmount();
    const bowlsView = await renderPage("cfb", { round: "bowls" });
    expect(screen.getByText("Top 25")).toBeInTheDocument();
    expect(linkTo("Completed")).toHaveAttribute("href", "/cfb?round=bowls&status=final");
    bowlsView.unmount();
    await renderPage("cfb", { round: "cfp-quarterfinals" });
    expect(screen.queryByText("Top 25")).not.toBeInTheDocument();
    expect(screen.queryByText("All conferences")).not.toBeInTheDocument();
  });

  test("PS-F13: a published slate with zero games shows the round copy", async () => {
    jest.mocked(getGames).mockResolvedValue([]);
    await renderPage("cfb", { round: "cfp-quarterfinals" });
    expect(screen.getByText("Matchups are set as each round is decided.")).toBeInTheDocument();
  });

  test("PS-F4: no postseason slates hides the toggle", async () => {
    jest.mocked(getSlates).mockResolvedValue([regular(11), regular(12)]);
    await renderPage("cfb", { week: "12" });
    expect(screen.queryByText("Postseason")).not.toBeInTheDocument();
    expect(screen.getByText("2026 Season · Week 12")).toBeInTheDocument();
  });

  test("PS-F3 / PS-F6: NFL takes games from the schedule by the slate week", async () => {
    jest.mocked(getSlates).mockResolvedValue([regular(17), regular(18), wildCard]);
    jest.mocked(getSchedule).mockResolvedValue({
      season: 2026,
      weeks: [
        { week: 18, games: [game({ game_id: "2026_18_BUF_NYJ" })] },
        { week: 19, games: [game({ game_id: "2026_19_KC_BUF" })] },
      ],
    });
    await renderPage("nfl", { round: "wild-card" });
    expect(getSlates).toHaveBeenCalledWith(2026, "NFL");
    expect(screen.getByText("2026 Postseason · Wild Card")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toHaveTextContent("2026_19_KC_BUF");
    expect(screen.queryByText("Top 25")).not.toBeInTheDocument();
  });

  it.each(["cfb", "nfl"])("PS-F13: a %s page whose API has no /api/slates yet shows the backend-down view", async (sport) => {
    const { NotFoundError } = jest.requireActual("@/lib/api");
    jest.mocked(getRecord).mockRejectedValue(new Error("no record"));
    jest.mocked(getSlates).mockRejectedValue(new NotFoundError("/api/slates"));
    jest.mocked(getSchedule).mockResolvedValue({ season: 2026, weeks: [], sport: "NFL" });
    jest.mocked(getGames).mockResolvedValue([]);
    await renderPage(sport);
    expect(screen.getByText(/reach the press box/)).toBeInTheDocument();
    expect(screen.queryByText("Select a week")).not.toBeInTheDocument();
  });
});
