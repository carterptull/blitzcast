/** OG share-image content shaping: buildOgContent().
 *
 *  This only tests the pure data-shaping logic that opengraph-image.tsx
 *  renders — not ImageResponse/satori itself. There's no established
 *  pattern in this repo for testing satori-rendered routes, and importing
 *  next/og pulls in the Node-only rendering pipeline (WASM font shaping,
 *  edge-style Response internals) that jsdom doesn't support cleanly.
 *  Actual pixel output was verified manually against a running server
 *  (see task-15-report.md) for finished/ready/pending/CFB/not-found cases. */

import { buildOgContent } from "../og";
import type { MatchupDetail } from "../types";

const base = (overrides: Partial<MatchupDetail> = {}): MatchupDetail =>
  ({
    game_id: "2026_01_BUF_KC",
    season: 2026,
    week: 1,
    sport: "NFL",
    home: { abbr: "KC", name: "Chiefs", record: "0-0", logo_url: null, win_prob: 0.58 },
    away: { abbr: "BUF", name: "Bills", record: "0-0", logo_url: null, win_prob: 0.42 },
    home_score: null,
    away_score: null,
    prediction_correct: null,
    ...overrides,
  }) as unknown as MatchupDetail;

describe("buildOgContent", () => {
  test("ready prediction: shows win probabilities, highlights the favorite", () => {
    const c = buildOgContent(base());
    expect(c.final).toBe(false);
    expect(c.hasProbs).toBe(true);
    expect(c.pending).toBe(false);
    expect(c.sub).toBe("Win probability");
    expect(c.away).toEqual({ abbr: "BUF", value: "42%", highlight: false });
    expect(c.home).toEqual({ abbr: "KC", value: "58%", highlight: true });
    expect(c.verdictText).toBeNull();
  });

  test("pending prediction: no probs yet", () => {
    const c = buildOgContent(
      base({
        home: { abbr: "KC", name: "Chiefs", record: "0-0", logo_url: null, win_prob: null },
        away: { abbr: "BUF", name: "Bills", record: "0-0", logo_url: null, win_prob: null },
      })
    );
    expect(c.final).toBe(false);
    expect(c.hasProbs).toBe(false);
    expect(c.pending).toBe(true);
    expect(c.away.value).toBe("—");
    expect(c.home.value).toBe("—");
    expect(c.away.highlight).toBe(false);
    expect(c.home.highlight).toBe(false);
    expect(c.verdictText).toBeNull();
  });

  test("finished game, model called it: shows scores, home wins, hit verdict", () => {
    const c = buildOgContent(base({ home_score: 27, away_score: 24, prediction_correct: true }));
    expect(c.final).toBe(true);
    expect(c.sub).toBe("Final");
    expect(c.away).toEqual({ abbr: "BUF", value: "24", highlight: false });
    expect(c.home).toEqual({ abbr: "KC", value: "27", highlight: true });
    expect(c.verdictText).toBe("Model called it");
    expect(c.verdictHit).toBe(true);
    expect(c.pending).toBe(false);
  });

  test("finished game, model missed: away team wins despite the model favoring home", () => {
    const c = buildOgContent(base({ home_score: 17, away_score: 20, prediction_correct: false }));
    expect(c.final).toBe(true);
    expect(c.away).toEqual({ abbr: "BUF", value: "20", highlight: true });
    expect(c.home).toEqual({ abbr: "KC", value: "17", highlight: false });
    expect(c.verdictText).toBe("Model missed");
    expect(c.verdictHit).toBe(false);
  });

  test("finished game with no prediction on record: no verdict text", () => {
    const c = buildOgContent(
      base({
        home_score: 27,
        away_score: 24,
        prediction_correct: null,
        home: { abbr: "KC", name: "Chiefs", record: "0-0", logo_url: null, win_prob: null },
        away: { abbr: "BUF", name: "Bills", record: "0-0", logo_url: null, win_prob: null },
      })
    );
    expect(c.final).toBe(true);
    expect(c.verdictText).toBeNull();
    expect(c.verdictHit).toBeNull();
  });

  test("NFL abbreviations use the display swap (LA -> LAR)", () => {
    const c = buildOgContent(
      base({
        home: { abbr: "LA", name: "Rams", record: "0-0", logo_url: null, win_prob: 0.5 },
      })
    );
    expect(c.home.abbr).toBe("LAR");
  });

  test("CFB games skip the NFL display-abbreviation swap and use the college league label", () => {
    const c = buildOgContent(base({ sport: "CFB" }));
    expect(c.league).toBe("College Football");
    expect(c.cfb).toBe(true);
    expect(c.home.abbr).toBe("KC"); // unchanged — no LA/LAR-style swap applies to CFB
  });

  test("NFL games use the NFL league label", () => {
    const c = buildOgContent(base());
    expect(c.league).toBe("NFL");
    expect(c.cfb).toBe(false);
  });

  test("a pick'em (0.5) game does not highlight either side", () => {
    const c = buildOgContent(
      base({
        home: { abbr: "KC", name: "Chiefs", record: "0-0", logo_url: null, win_prob: 0.5 },
        away: { abbr: "BUF", name: "Bills", record: "0-0", logo_url: null, win_prob: 0.5 },
      })
    );
    expect(c.away.highlight).toBe(false);
    expect(c.home.highlight).toBe(false);
  });

  test("a tied final does not highlight either side", () => {
    const c = buildOgContent(base({ home_score: 20, away_score: 20, prediction_correct: null }));
    expect(c.away.highlight).toBe(false);
    expect(c.home.highlight).toBe(false);
  });
});
