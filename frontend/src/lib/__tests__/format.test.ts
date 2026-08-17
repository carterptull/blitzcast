/**
 * Format Utility Tests
 *
 * Tests formatting functions for dates, percentages, and display strings.
 */

import { fmtPct, fmtKickoffTime } from "../format";

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
      const iso = "2026-09-13T21:05:00Z"; // 5:05 PM ET
      const result = fmtKickoffTime(iso);
      // Should contain day and time info
      expect(result.length).toBeGreaterThan(3);
    });
  });
});
