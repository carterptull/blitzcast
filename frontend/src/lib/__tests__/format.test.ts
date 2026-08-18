/** Formatting helpers: percentages, kickoff times, spreads. */

import {
  fmtPct,
  fmtKickoffTime,
  fmtSpread,
  pickDefaultWeek,
  pickCfbDefaultWeek,
} from "../format";
import type { MatchupDetail, Odds, Schedule } from "../types";

/** Weeks of games with only the kickoff field pickDefaultWeek reads. */
const schedule = (weeks: (string | null)[][]): Schedule =>
  ({
    season: 2026,
    weeks: weeks.map((kickoffs, i) => ({
      week: i + 1,
      games: kickoffs.map((kickoff) => ({ kickoff })),
    })),
  }) as unknown as Schedule;

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

    test("no odds renders a dash", () => {
      expect(fmtSpread(matchup(null))).toBe("—");
    });

    test("odds present but spread missing renders a dash", () => {
      expect(fmtSpread(matchup({ total: 48.5 }))).toBe("—");
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

  describe("pickDefaultWeek", () => {
    const now = new Date("2026-09-20T12:00:00Z");

    test("returns the first week with an upcoming game", () => {
      const s = schedule([["2026-09-13T17:00:00Z"], ["2026-09-27T17:00:00Z"]]);
      expect(pickDefaultWeek(s, now)).toBe(2);
    });

    test("a leftover TBD does not pin a finished week", () => {
      // Week 1 has played out except for one game that never got a time.
      const s = schedule([["2026-09-13T17:00:00Z", null], ["2026-09-27T17:00:00Z"]]);
      expect(pickDefaultWeek(s, now)).toBe(2);
    });

    test("a week with nothing scheduled yet is still ahead", () => {
      const s = schedule([["2026-09-13T17:00:00Z"], [null, null]]);
      expect(pickDefaultWeek(s, now)).toBe(2);
    });

    test("sticks to the last week once the season is over", () => {
      const s = schedule([["2026-09-13T17:00:00Z"], ["2026-09-14T17:00:00Z"]]);
      expect(pickDefaultWeek(s, new Date("2027-01-01T00:00:00Z"))).toBe(2);
    });

    // A realistic NFL week: a Sunday afternoon slate plus Monday Night Football.
    // 2026-09-15T00:15Z is Mon Sep 14, 8:15 PM ET.
    const withMnf = () =>
      schedule([
        ["2026-09-13T17:00:00Z", "2026-09-15T00:15:00Z"],
        ["2026-09-20T17:00:00Z", "2026-09-22T00:15:00Z"],
      ]);

    test("Monday afternoon shows the current week, MNF has not kicked off", () => {
      // Mon Sep 14, 6:00 PM ET
      expect(pickDefaultWeek(withMnf(), new Date("2026-09-14T22:00:00Z"))).toBe(1);
    });

    test("late Monday night still shows the week just played", () => {
      // Mon Sep 14, 11:30 PM ET, right after MNF ends
      expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T03:30:00Z"))).toBe(1);
    });

    test("early Tuesday still shows the finished week", () => {
      // Tue Sep 15, 7:00 AM ET. This is the case the 6h hold gets wrong:
      // it rolled over at 2:15 AM and would return 2 here.
      expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T11:00:00Z"))).toBe(1);
    });

    test("by Tuesday mid-morning it has rolled to the new week", () => {
      // Tue Sep 15, 10:00 AM ET
      expect(pickDefaultWeek(withMnf(), new Date("2026-09-15T14:00:00Z"))).toBe(2);
    });
  });

  describe("pickCfbDefaultWeek", () => {
    test("Sunday night ET is still the outgoing week", () => {
      // Sun Sep 6, 8:00 PM ET. Anchoring at plain UTC rolled this to week 2.
      expect(pickCfbDefaultWeek(new Date("2026-09-07T00:00:00Z"))).toBe(1);
    });

    test("Monday midnight ET starts the new week", () => {
      expect(pickCfbDefaultWeek(new Date("2026-09-07T04:00:00Z"))).toBe(2);
    });

    test("clamps before the season and after the finale", () => {
      expect(pickCfbDefaultWeek(new Date("2026-06-01T00:00:00Z"))).toBe(1);
      expect(pickCfbDefaultWeek(new Date("2027-03-01T00:00:00Z"))).toBe(15);
    });
  });
});
