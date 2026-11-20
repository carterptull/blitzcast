/** Formatting helpers: percentages, kickoff times, spreads. */

import {
  eyebrowText,
  fmtPct,
  fmtKickoffTime,
  fmtSpread,
  pickDefaultSlate,
  resolveSlate,
  slateHref,
} from "../format";
import * as format from "../format";
import type { MatchupDetail, Odds, Round, Slate } from "../types";

/** Only the fields fmtSpread reads. */
const matchup = (odds: Partial<Odds> | null, sport: "NFL" | "CFB" = "NFL") =>
  ({
    sport,
    home: { abbr: "KC" },
    away: { abbr: "BUF" },
    odds: odds && {
      spread_home: null,
      moneyline_home: null,
      moneyline_away: null,
      total: null,
      ...odds,
    },
  }) as unknown as MatchupDetail;

describe("Format Utilities", () => {
  describe("fmtPct", () => {
    test("formats 0.5 as 50%", () => {
      expect(fmtPct(0.5)).toBe("50%");
    });

    test("formats 0.625 as 63%", () => {
      expect(fmtPct(0.625)).toBe("63%");
    });

    test("formats 0.0 as 0%", () => {
      expect(fmtPct(0.0)).toBe("0%");
    });

    test("formats 1.0 as 100%", () => {
      expect(fmtPct(1.0)).toBe("100%");
    });

    test("formats 0.333 as 33%", () => {
      expect(fmtPct(0.333)).toBe("33%");
    });

    test("rounds correctly for near-boundary values", () => {
      expect(fmtPct(0.995)).toBe("100%");
      expect(fmtPct(0.005)).toBe("1%");
    });
  });

  describe("fmtKickoffTime", () => {
    test("formats Thursday game correctly", () => {
      const thu = new Date("2026-09-10T20:20:00Z").toISOString();
      const result = fmtKickoffTime(thu);
      // 20:20 UTC is 4:20 PM ET
      expect(result).toMatch(/^\d{1,2}:\d{2}\s(AM|PM)\sET$/);
      expect(result).toContain("4:20");
    });

    test("formats Sunday game correctly", () => {
      const sun = new Date("2026-09-13T17:00:00Z").toISOString();
      const result = fmtKickoffTime(sun);
      // 17:00 UTC is 1:00 PM ET
      expect(result).toMatch(/^\d{1,2}:\d{2}\s(AM|PM)\sET$/);
      expect(result).toContain("1:00");
    });

    test("handles ISO string input", () => {
      const iso = "2026-09-14T00:15:00Z";
      const result = fmtKickoffTime(iso);
      expect(result).toBeDefined();
      expect(typeof result).toBe("string");
    });

    test("returns readable time format", () => {
      const iso = "2026-09-13T21:05:00Z";
      expect(fmtKickoffTime(iso).length).toBeGreaterThan(3);
    });
  });

  describe("fmtSpread", () => {
    // spread_home is positive when the home team is favored (nflverse).
    test("positive spread names the home team", () => {
      expect(fmtSpread(matchup({ spread_home: 7 }))).toBe("KC -7");
    });

    test("negative spread names the away team", () => {
      expect(fmtSpread(matchup({ spread_home: -3.5 }))).toBe("BUF -3.5");
    });

    test("zero is a pick'em", () => {
      expect(fmtSpread(matchup({ spread_home: 0 }))).toBe("PK");
    });

    test("no odds renders N/A", () => {
      expect(fmtSpread(matchup(null))).toBe("N/A");
    });

    test("odds present but spread missing renders N/A", () => {
      expect(fmtSpread(matchup({ total: 48.5 }))).toBe("N/A");
    });

    test("agrees with the moneyline favorite", () => {
      // Home favorite: negative home moneyline, positive spread_home.
      const home = matchup({ spread_home: 7, moneyline_home: -330 });
      expect(fmtSpread(home).startsWith("KC")).toBe(true);
      const away = matchup({ spread_home: -4.5, moneyline_away: -200 });
      expect(fmtSpread(away).startsWith("BUF")).toBe(true);
    });

    test("CFB keeps its own abbreviations", () => {
      expect(fmtSpread(matchup({ spread_home: 6 }, "CFB"))).toBe("KC -6");
    });
  });
});

// Slate fixtures from the 2026-27 calendar (spec section 2). Each slate is
// shaped the way /api/slates computes it at `now`: next_kickoff is the
// earliest kickoff later than now minus 12 hours.
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const shift = (iso: string, days: number) => new Date(Date.parse(iso) + days * DAY).toISOString();

interface Spec {
  key: string;
  week: number;
  round?: Round;
  label?: string;
  group: string;
  short: string;
  kickoffs: (string | null)[];
  /** When the rows first exist in the feed. */
  appears?: string;
}

function build(specs: Spec[], now: Date): Slate[] {
  const cutoff = now.getTime() - 12 * HOUR;
  return specs
    .filter((s) => !s.appears || Date.parse(s.appears) <= now.getTime())
    .map((s) => {
      const dated = s.kickoffs.filter((k): k is string => k !== null).sort();
      return {
        key: s.key,
        phase: s.round && s.round !== "conf_championship" ? "postseason" : "regular",
        week: s.week,
        round: s.round ?? null,
        label: s.label ?? null,
        group_label: s.group,
        short_label: s.short,
        game_count: s.kickoffs.length,
        first_kickoff: dated[0] ?? null,
        next_kickoff: dated.find((k) => Date.parse(k) > cutoff) ?? null,
        has_unscheduled: s.kickoffs.some((k) => k === null),
        last_kickoff: dated[dated.length - 1] ?? null,
      };
    });
}

const regularWeek = (week: number, kickoffs: string[]): Spec => ({
  key: `w${week}`,
  week,
  group: "Wk",
  short: String(week),
  kickoffs,
});

const CFB_POST = "2026-12-06T22:00:00Z";
const CFB: Spec[] = [
  ...Array.from({ length: 13 }, (_, i) => {
    const sat = shift("2026-09-05T16:00:00Z", 7 * i);
    return regularWeek(i + 1, [sat, shift(sat, 8.5 / 24)]);
  }),
  {
    key: "w14",
    week: 14,
    round: "conf_championship",
    label: "Conference Championships",
    group: "Champ",
    short: "14",
    kickoffs: ["2026-12-05T01:00:00Z", "2026-12-05T17:00:00Z", "2026-12-06T01:00:00Z"],
  },
  regularWeek(15, ["2026-12-12T20:00:00Z"]),
  {
    key: "bowls",
    week: 17,
    round: "bowl",
    label: "Bowl Season",
    group: "Non-CFP",
    short: "Bowls",
    appears: CFB_POST,
    kickoffs: [
      "2026-12-15T23:00:00Z",
      "2026-12-17T23:00:00Z",
      "2026-12-20T20:00:00Z",
      "2026-12-22T17:30:00Z",
      "2026-12-26T20:00:00Z",
      "2026-12-27T20:00:00Z",
      "2026-12-31T17:00:00Z",
      "2027-01-02T20:00:00Z",
    ],
  },
  {
    key: "cfp-first-round",
    week: 17,
    round: "cfp_first_round",
    label: "CFP First Round",
    group: "CFP",
    short: "R1",
    appears: CFB_POST,
    kickoffs: [
      "2026-12-19T01:00:00Z",
      "2026-12-19T17:00:00Z",
      "2026-12-19T20:30:00Z",
      "2026-12-20T00:30:00Z",
    ],
  },
  {
    key: "cfp-quarterfinals",
    week: 17,
    round: "cfp_quarterfinal",
    label: "CFP Quarterfinals",
    group: "CFP",
    short: "QF",
    appears: CFB_POST,
    kickoffs: [
      "2026-12-31T00:30:00Z",
      "2027-01-01T17:00:00Z",
      "2027-01-01T21:00:00Z",
      "2027-01-02T01:00:00Z",
    ],
  },
  {
    key: "cfp-semifinals",
    week: 17,
    round: "cfp_semifinal",
    label: "CFP Semifinals",
    group: "CFP",
    short: "SF",
    appears: CFB_POST,
    kickoffs: ["2027-01-15T00:30:00Z", "2027-01-16T00:30:00Z"],
  },
  {
    key: "cfp-title",
    week: 17,
    round: "cfp_championship",
    label: "National Championship",
    group: "CFP",
    short: "Title",
    appears: "2027-01-16T06:00:00Z",
    kickoffs: ["2027-01-26T00:30:00Z"],
  },
];

const NFL: Spec[] = [
  ...Array.from({ length: 17 }, (_, i) =>
    regularWeek(i + 1, [
      shift("2026-09-11T00:20:00Z", 7 * i),
      shift("2026-09-13T17:00:00Z", 7 * i),
      shift("2026-09-15T00:15:00Z", 7 * i),
    ])
  ),
  regularWeek(18, ["2027-01-09T21:30:00Z", "2027-01-10T18:00:00Z", "2027-01-11T01:20:00Z"]),
  {
    key: "wild-card",
    week: 19,
    round: "wild_card",
    label: "Wild Card",
    group: "Round",
    short: "WC",
    appears: "2027-01-11T06:00:00Z",
    kickoffs: [
      "2027-01-16T21:30:00Z",
      "2027-01-17T01:15:00Z",
      "2027-01-17T18:00:00Z",
      "2027-01-17T21:30:00Z",
      "2027-01-18T01:15:00Z",
      "2027-01-18T21:30:00Z",
    ],
  },
  {
    key: "divisional",
    week: 20,
    round: "divisional",
    label: "Divisional",
    group: "Round",
    short: "DIV",
    appears: "2027-01-19T06:00:00Z",
    kickoffs: [
      "2027-01-23T21:30:00Z",
      "2027-01-24T01:15:00Z",
      "2027-01-24T18:00:00Z",
      "2027-01-24T21:30:00Z",
    ],
  },
  {
    key: "conference",
    week: 21,
    round: "conference",
    label: "Conference Championships",
    group: "Round",
    short: "CONF",
    appears: "2027-01-25T06:00:00Z",
    kickoffs: ["2027-01-31T20:00:00Z", "2027-02-01T00:30:00Z"],
  },
  {
    key: "super-bowl",
    week: 22,
    round: "super_bowl",
    label: "Super Bowl",
    group: "Round",
    short: "SB",
    appears: "2027-02-01T06:00:00Z",
    kickoffs: ["2027-02-14T23:30:00Z"],
  },
];

const at = (date: string) => new Date(`${date}T15:00:00Z`);
const cfbOn = (date: string) => build(CFB, at(date));
const nflOn = (date: string) => build(NFL, at(date));

describe("pickDefaultSlate", () => {
  describe("PS-F2 / PS-V1: Appendix E default slate table", () => {
    test.each([
      ["CFB", "2026-11-19", "w12"],
      ["CFB", "2026-12-01", "w14"],
      ["CFB", "2026-12-08", "bowls"],
      ["CFB", "2026-12-14", "cfp-first-round"],
      ["CFB", "2026-12-21", "bowls"],
      ["CFB", "2026-12-26", "cfp-quarterfinals"],
      ["CFB", "2027-01-04", "cfp-semifinals"],
      ["CFB", "2027-01-20", "cfp-title"],
      ["NFL", "2027-01-05", "w18"],
      ["NFL", "2027-01-12", "wild-card"],
      ["NFL", "2027-01-20", "divisional"],
      ["NFL", "2027-01-26", "conference"],
      ["NFL", "2027-02-03", "super-bowl"],
    ])("%s on %s opens %s", (sport, date, key) => {
      const slates = sport === "CFB" ? cfbOn(date) : nflOn(date);
      expect(pickDefaultSlate(slates, at(date))?.key).toBe(key);
    });

    test("PS-V1: the Week 14 default carries the Conference Championships eyebrow", () => {
      const slate = pickDefaultSlate(cfbOn("2026-12-01"), at("2026-12-01"));
      expect(eyebrowText(2026, slate as Slate)).toBe("2026 Season · Conference Championships");
    });
  });

  test("PS-F1: with no postseason slates, mid-November opens the current regular week", () => {
    const slates = cfbOn("2026-11-19");
    expect(slates.every((s) => s.phase === "regular")).toBe(true);
    expect(pickDefaultSlate(slates, at("2026-11-19"))?.key).toBe("w12");
    expect(pickDefaultSlate(nflOn("2026-11-19"), at("2026-11-19"))?.key).toBe("w11");
  });

  test("PS-F1: postseason candidates win over a live regular week", () => {
    const slates = cfbOn("2026-12-08");
    expect(slates.find((s) => s.key === "w15")?.next_kickoff).not.toBeNull();
    expect(pickDefaultSlate(slates, at("2026-12-08"))?.phase).toBe("postseason");
  });

  test("PS-F1: an unscheduled-only slate sorts after dated ones", () => {
    const now = at("2026-12-08");
    const specs: Spec[] = [
      { key: "bowls", week: 17, round: "bowl", group: "Non-CFP", short: "Bowls", kickoffs: [null] },
      {
        key: "cfp-first-round",
        week: 17,
        round: "cfp_first_round",
        group: "CFP",
        short: "R1",
        kickoffs: ["2026-12-19T01:00:00Z"],
      },
    ];
    expect(pickDefaultSlate(build(specs, now), now)?.key).toBe("cfp-first-round");
    expect(pickDefaultSlate(build(specs.slice(0, 1), now), now)?.key).toBe("bowls");
  });

  test("PS-F1: when nothing is live the last candidate wins", () => {
    const now = at("2027-03-01");
    expect(pickDefaultSlate(build(CFB, now), now)?.key).toBe("cfp-title");
    expect(pickDefaultSlate(build(NFL.slice(0, 18), now), now)?.key).toBe("w18");
  });

  test("PS-F1: no slates at all yields undefined", () => {
    expect(pickDefaultSlate([], at("2026-11-19"))).toBeUndefined();
  });
});

describe("resolveSlate", () => {
  const now = at("2026-12-08");
  const cfb = cfbOn("2026-12-08");

  test("PS-F3 / PS-V2: ?week=14 opens Week 14 even when postseason exists", () => {
    expect(resolveSlate(cfb, { week: "14" }, now)?.key).toBe("w14");
  });

  test("PS-F3: ?round=bowls opens the bowls slate", () => {
    expect(resolveSlate(cfb, { round: "bowls" }, now)?.key).toBe("bowls");
  });

  test("PS-F3: an unknown round falls back to the default", () => {
    expect(resolveSlate(cfb, { round: "bogus" }, now)?.key).toBe("bowls");
  });

  test("PS-F3: a postseason week typed as ?week=17 falls back to the default", () => {
    expect(resolveSlate(cfb, { week: "17" }, now)?.key).toBe("bowls");
  });

  test("PS-F3: a malformed or missing week falls back to the default", () => {
    expect(resolveSlate(cfb, { week: "14abc" }, now)?.key).toBe("bowls");
    expect(resolveSlate(cfb, {}, now)?.key).toBe("bowls");
  });

  test("PS-F3: a slug from the other sport falls back to the default", () => {
    const nflNow = at("2027-01-12");
    expect(resolveSlate(nflOn("2027-01-12"), { round: "bowls" }, nflNow)?.key).toBe("wild-card");
  });
});

describe("slateHref", () => {
  const cfb = cfbOn("2026-12-08");
  const byKey = (k: string) => cfb.find((s) => s.key === k) as Slate;

  test("PS-F5: regular slates link by week, postseason by round slug", () => {
    expect(slateHref("/cfb", byKey("w14"))).toBe("/cfb?week=14");
    expect(slateHref("/cfb", byKey("bowls"), "&conf=SEC")).toBe("/cfb?round=bowls&conf=SEC");
  });
});

describe("eyebrowText", () => {
  test.each([
    ["w12", "2026 Season · Week 12", cfbOn("2026-11-19")],
    ["w14", "2026 Season · Conference Championships", cfbOn("2026-12-01")],
    ["wild-card", "2026 Postseason · Wild Card", nflOn("2027-01-12")],
    ["cfp-quarterfinals", "2026 Postseason · CFP Quarterfinals", cfbOn("2026-12-26")],
  ])("PS-F6: %s reads %s", (key, text, slates) => {
    expect(eyebrowText(2026, slates.find((s) => s.key === key) as Slate)).toBe(text);
  });
});

test("PS-F12: the calendar-based week helpers are gone", () => {
  for (const name of ["CFB_WEEKS", "pickCfbDefaultWeek", "pickDefaultWeek"]) {
    expect(name in format).toBe(false);
  }
});
