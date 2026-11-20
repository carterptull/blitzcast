/** Matchup page helpers: separator, title and back link. */

import { backLink, matchupSeparator, matchupTitle, occasionLabel } from "../matchup";
import { REGULAR_OCCASION } from "../occasion";
import type { MatchupDetail, Occasion } from "../types";

function matchup(
  overrides: Partial<MatchupDetail> & { neutral?: boolean } = {}
): MatchupDetail {
  const { neutral = false, ...rest } = overrides;
  return {
    game_id: "2026_05_KC_BUF",
    season: 2026,
    week: 5,
    kickoff: "2026-10-05T17:00:00Z",
    venue: { name: "Stadium", city: "City", is_dome: false, is_neutral_site: neutral },
    is_primetime: false,
    is_divisional: false,
    home: { abbr: "BUF", name: "Bills", record: "3-1", logo_url: null, win_prob: 0.6 },
    away: { abbr: "KC", name: "Chiefs", record: "4-0", logo_url: null, win_prob: 0.4 },
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
    ...rest,
  };
}

const post = (round: Occasion["round"], event_name: string): Partial<MatchupDetail> => ({
  season_type: "postseason",
  round,
  event_name,
});

describe("matchupSeparator", () => {
  it("PS-F8: neutral sites read vs, home games keep @", () => {
    expect(matchupSeparator(true)).toBe("vs");
    expect(matchupSeparator(false)).toBe("@");
  });
});

describe("occasionLabel", () => {
  it("PS-F8: event name wins, else Week N", () => {
    expect(occasionLabel(matchup())).toBe("Week 5");
    expect(occasionLabel(matchup(post("super_bowl", "Super Bowl LXI")))).toBe("Super Bowl LXI");
  });
});

describe("matchupTitle", () => {
  it("PS-F8: neutral Super Bowl reads BUF vs DET, Super Bowl LXI", () => {
    const m = matchup({
      ...post("super_bowl", "Super Bowl LXI"),
      week: 22,
      neutral: true,
      away: { abbr: "BUF", name: "Bills", record: "14-3", logo_url: null, win_prob: 0.5 },
      home: { abbr: "DET", name: "Lions", record: "13-4", logo_url: null, win_prob: 0.5 },
    });
    expect(matchupTitle(m)).toBe("BUF vs DET, Super Bowl LXI");
  });

  it("PS-F8: regular game reads KC @ BUF, Week 5", () => {
    expect(matchupTitle(matchup())).toBe("KC @ BUF, Week 5");
  });

  it("PS-F8: NFL abbreviations use the display swap; CFB keeps its own", () => {
    const nfl = matchup({ home: { abbr: "LA", name: "Rams", record: "0-0", logo_url: null, win_prob: 0.5 } });
    expect(matchupTitle(nfl)).toBe("KC @ LAR, Week 5");
    const cfb = matchup({
      sport: "CFB",
      week: 14,
      season_type: "regular",
      round: "conf_championship",
      event_name: "SEC Championship",
      neutral: true,
      away: { abbr: "UGA", name: "Georgia", record: "11-1", logo_url: null, win_prob: 0.5 },
      home: { abbr: "LA", name: "Louisiana", record: "11-1", logo_url: null, win_prob: 0.5 },
    });
    expect(matchupTitle(cfb)).toBe("UGA vs LA, SEC Championship");
  });
});

describe("backLink", () => {
  it("PS-F8: an NFL playoff game goes back to its round", () => {
    const m = matchup({ ...post("wild_card", "AFC Wild Card"), week: 19 });
    expect(backLink(m, "nfl")).toEqual({ href: "/nfl?round=wild-card", label: "Back to Wild Card" });
  });

  it("PS-F8: a regular game goes back to its week slate", () => {
    expect(backLink(matchup(), "nfl")).toEqual({ href: "/nfl?week=5", label: "Week 5 slate" });
  });

  it("PS-F8: a CFB bowl goes back to Bowl Season", () => {
    const m = matchup({ ...post("bowl", "Duke's Mayo Bowl"), sport: "CFB", week: 17 });
    expect(backLink(m, "cfb")).toEqual({ href: "/cfb?round=bowls", label: "Back to Bowl Season" });
  });

  it("PS-V3: a CFB title game is a regular week 14 game", () => {
    const m = matchup({
      sport: "CFB",
      week: 14,
      round: "conf_championship",
      event_name: "SEC Championship",
    });
    expect(backLink(m, "cfb")).toEqual({ href: "/cfb?week=14", label: "Week 14 slate" });
  });

  it("PS-F8: every postseason round maps to its slate slug", () => {
    const cases: [Occasion["round"], string, string][] = [
      ["divisional", "divisional", "Divisional"],
      ["conference", "conference", "Conference Championships"],
      ["super_bowl", "super-bowl", "Super Bowl"],
      ["cfp_first_round", "cfp-first-round", "CFP First Round"],
      ["cfp_quarterfinal", "cfp-quarterfinals", "CFP Quarterfinals"],
      ["cfp_semifinal", "cfp-semifinals", "CFP Semifinals"],
      ["cfp_championship", "cfp-title", "National Championship"],
      ["cfp_other", "cfp-other", "College Football Playoff"],
    ];
    for (const [round, slug, label] of cases) {
      const m = matchup({ ...post(round, "Event"), week: 17 });
      expect(backLink(m, "cfb")).toEqual({ href: `/cfb?round=${slug}`, label: `Back to ${label}` });
    }
  });

  it("PS-F8: a postseason game with an unknown round falls back to its week", () => {
    const m = matchup({ season_type: "postseason", round: null, week: 20 });
    expect(backLink(m, "nfl")).toEqual({ href: "/nfl?week=20", label: "Week 20 slate" });
  });
});
