/** Postseason contract: GameSummary/MatchupDetail fields, slates, and mock fixtures. */

describe("postseason contract", () => {
  const originalEnv = process.env;
  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv, NEXT_PUBLIC_USE_MOCK: "1" };
  });
  afterEach(() => {
    process.env = originalEnv;
  });

  test("PS-A1: every mock game carries the postseason fields with exact nullability", async () => {
    const { mockSchedule } = await import("../mock");
    for (const sport of ["NFL", "CFB"] as const) {
      for (const w of mockSchedule(sport).weeks) {
        for (const g of w.games) {
          expect(["regular", "postseason"]).toContain(g.season_type);
          expect(g.round === null || typeof g.round === "string").toBe(true);
          expect(g.event_name === null || typeof g.event_name === "string").toBe(true);
          expect(typeof g.is_neutral_site).toBe("boolean");
          expect(g.home_seed === null || typeof g.home_seed === "number").toBe(true);
          expect(g.away_seed === null || typeof g.away_seed === "number").toBe(true);
        }
      }
    }
  });

  test("PS-A1: matchup detail carries season type, round, event and seeds", async () => {
    const { getMatchup } = await import("../api");
    const sb = await getMatchup("2026_22_KC_PHI");
    expect(sb.season_type).toBe("postseason");
    expect(sb.round).toBe("super_bowl");
    expect(sb.event_name).toBe("Super Bowl LXI");
    expect(sb.venue.is_neutral_site).toBe(true);
    expect(sb.home_seed).toBeNull();
    const regular = await getMatchup("2026_01_BUF_KC");
    expect(regular.season_type).toBe("regular");
    expect(regular.round).toBeNull();
    expect(regular.event_name).toBeNull();
  });

  test("PS-D5: the frontend round list matches the backend's 11 rounds", async () => {
    const { ROUNDS } = await import("../occasion");
    expect(ROUNDS).toEqual([
      "conf_championship", "wild_card", "divisional", "conference", "super_bowl", "bowl",
      "cfp_first_round", "cfp_quarterfinal", "cfp_semifinal", "cfp_championship", "cfp_other",
    ]);
  });

  test("PS-A6: mock slates cover regular weeks and every postseason round fixture", async () => {
    const { getSlates } = await import("../api");
    const nfl = await getSlates(2026, "NFL");
    expect(nfl.filter((s) => s.phase === "postseason").map((s) => s.key)).toEqual([
      "wild-card", "divisional", "conference", "super-bowl",
    ]);
    expect(nfl.filter((s) => s.phase === "regular")).toHaveLength(18);
    const cfb = await getSlates(2026, "CFB");
    const w14 = cfb.find((s) => s.key === "w14");
    expect(w14?.label).toBe("Conference Championships");
    expect(w14?.group_label).toBe("Champ");
    expect(cfb.filter((s) => s.phase === "postseason").map((s) => s.key)).toEqual([
      "bowls", "cfp-first-round", "cfp-quarterfinals",
    ]);
    const bowls = cfb.find((s) => s.key === "bowls");
    expect(bowls?.week).toBe(17);
    expect(bowls?.has_unscheduled).toBe(true);
  });

  test("PS-A6: getGames filters a postseason week by round slug", async () => {
    const { getGames } = await import("../api");
    const bowls = await getGames(17, 2026, "CFB", "all", "bowls");
    expect(bowls.length).toBe(2);
    expect(bowls.every((g) => g.round === "bowl")).toBe(true);
    const r1 = await getGames(17, 2026, "CFB", "all", "cfp-first-round");
    expect(r1.every((g) => g.home_seed !== null && g.away_seed !== null)).toBe(true);
    const all17 = await getGames(17, 2026, "CFB");
    expect(all17.length).toBe(5);
  });

  test("PS-A6: getGames passes the round slug to the live API", async () => {
    delete process.env.NEXT_PUBLIC_USE_MOCK;
    const fetchSpy = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    const original = global.fetch;
    global.fetch = fetchSpy as unknown as typeof fetch;
    try {
      const { getGames, getSlates } = await import("../api");
      await getGames(17, 2026, "CFB", "all", "bowls");
      expect(fetchSpy.mock.calls[0][0]).toContain(
        "/api/games?week=17&season=2026&sport=CFB&status=all&round=bowls"
      );
      await getSlates(2026, "CFB");
      expect(fetchSpy.mock.calls[1][0]).toContain("/api/slates?season=2026&sport=CFB");
    } finally {
      global.fetch = original;
    }
  });

  test("PS-A6: mock event names never contain an en or em dash", async () => {
    const { mockSchedule } = await import("../mock");
    const names = (["NFL", "CFB"] as const).flatMap((s) =>
      mockSchedule(s).weeks.flatMap((w) => w.games.map((g) => g.event_name ?? ""))
    );
    expect(names.filter(Boolean).length).toBeGreaterThan(5);
    for (const n of names) expect(/[–—]/.test(n)).toBe(false);
  });
});
