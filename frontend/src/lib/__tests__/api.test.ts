/** API client tests: error handling, mock mode, and contract validation. */

import { ApiUnreachableError, NotFoundError } from "../api";

describe("API Client", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe("Error Classes", () => {
    test("ApiUnreachableError has correct name", () => {
      const err = new ApiUnreachableError("test");
      expect(err.name).toBe("ApiUnreachableError");
      expect(err.message).toContain("test");
    });

    test("ApiUnreachableError default message includes API URL", () => {
      const err = new ApiUnreachableError();
      expect(err.message).toContain("http://localhost:8000");
    });

    test("NotFoundError has correct name", () => {
      const err = new NotFoundError("/api/test");
      expect(err.name).toBe("NotFoundError");
      expect(err.message).toContain("/api/test");
    });
  });

  describe("Mock Mode", () => {
    beforeEach(() => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
    });

    test("getTeams returns mock data in mock mode", async () => {
      expect(process.env.NEXT_PUBLIC_USE_MOCK).toBe("1");

      // Re-import to pick up env change
      const { getTeams: getMockTeams } = await import("../api");
      const teams = await getMockTeams("NFL");

      expect(teams).toBeDefined();
      expect(Array.isArray(teams)).toBe(true);
      expect(teams.length).toBeGreaterThan(0);
      expect(teams[0]).toHaveProperty("abbr");
      expect(teams[0]).toHaveProperty("name");
    });

    test("getSchedule returns mock data in mock mode", async () => {
      const { getSchedule: getMockSchedule } = await import("../api");
      const schedule = await getMockSchedule(2026, "NFL");

      expect(schedule).toBeDefined();
      expect(schedule).toHaveProperty("season");
      expect(schedule).toHaveProperty("weeks");
      expect(Array.isArray(schedule.weeks)).toBe(true);
    });

    test("getGames returns mock data in mock mode", async () => {
      const { getGames: getMockGames } = await import("../api");
      const games = await getMockGames(1, 2026, "NFL");

      expect(games).toBeDefined();
      expect(Array.isArray(games)).toBe(true);
    });

    test("getMatchup returns mock matchup data in mock mode", async () => {
      const { getMatchup: getMockMatchup } = await import("../api");
      const matchup = await getMockMatchup("2026_01_BUF_KC");

      expect(matchup).toBeDefined();
      expect(matchup).toHaveProperty("game_id");
      expect(matchup).toHaveProperty("home");
      expect(matchup).toHaveProperty("away");
    });

    test("getMatchup throws NotFoundError for unknown game in mock mode", async () => {
      const { getMatchup: getMockMatchup, NotFoundError: ImportedNotFoundError } = await import("../api");

      try {
        await getMockMatchup("unknown_game");
        fail("Expected NotFoundError to be thrown");
      } catch (error) {
        expect(error).toBeInstanceOf(ImportedNotFoundError);
        expect((error as Error).message).toContain("Not found");
      }
    });
  });

  describe("Contract Validation", () => {
    test("Team contract has required fields", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getTeams: getMockTeams } = await import("../api");
      const teams = await getMockTeams("NFL");

      expect(teams.length).toBeGreaterThan(0);
      const team = teams[0];
      expect(team).toHaveProperty("id");
      expect(team).toHaveProperty("abbr");
      expect(team).toHaveProperty("name");
      expect(team).toHaveProperty("conference");
    });

    test("GameSummary contract has required fields", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getGames: getMockGames } = await import("../api");
      const games = await getMockGames(1, 2026, "NFL");

      expect(games.length).toBeGreaterThan(0);
      const game = games[0];
      expect(game).toHaveProperty("game_id");
      expect(game).toHaveProperty("home");
      expect(game).toHaveProperty("away");
      expect(game).toHaveProperty("status");
      expect(game).toHaveProperty("has_prediction");
    });

    test("MatchupDetail contract has required fields", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getMatchup: getMockMatchup } = await import("../api");
      const matchup = await getMockMatchup("2026_01_BUF_KC");

      expect(matchup).toHaveProperty("game_id");
      expect(matchup).toHaveProperty("season");
      expect(matchup).toHaveProperty("week");
      expect(matchup).toHaveProperty("home");
      expect(matchup).toHaveProperty("away");
      expect(matchup).toHaveProperty("prediction_status");
      expect(["ready", "pending"]).toContain(matchup.prediction_status);
    });
  });

  describe("Sport Parameter", () => {
    test("getTeams accepts NFL sport", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getTeams: getMockTeams } = await import("../api");
      const teams = await getMockTeams("NFL");
      expect(Array.isArray(teams)).toBe(true);
    });

    test("getTeams accepts CFB sport", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getTeams: getMockTeams } = await import("../api");
      const teams = await getMockTeams("CFB");
      expect(Array.isArray(teams)).toBe(true);
    });

    test("getSchedule defaults to NFL sport", async () => {
      process.env.NEXT_PUBLIC_USE_MOCK = "1";
      const { getSchedule: getMockSchedule } = await import("../api");
      const schedule = await getMockSchedule(2026);
      expect(schedule).toBeDefined();
    });
  });
});
