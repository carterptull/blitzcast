// Fixture data for NEXT_PUBLIC_USE_MOCK=1 — a realistic fake 2026 Week 1
// slate with full predictions, plus generated schedule-only weeks 2–18.

import { TEAMS, TEAM_ABBRS, logoUrl } from "./teams";
import type {
  Factor,
  GameSummary,
  MatchupDetail,
  Odds,
  Schedule,
  Team,
  Weather,
} from "./types";

const SEASON = 2026;
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
// Week 1 anchors (UTC; September ET is UTC-4).
const THU = Date.UTC(2026, 8, 11, 0, 20); // Thu Sep 10, 8:20 PM ET
const SUN_EARLY = Date.UTC(2026, 8, 13, 17, 0); // Sun Sep 13, 1:00 PM ET
const SUN_LATE = Date.UTC(2026, 8, 13, 20, 5); // 4:05 PM ET
const SUN_LATE_2 = Date.UTC(2026, 8, 13, 20, 25); // 4:25 PM ET
const SNF = Date.UTC(2026, 8, 14, 0, 20); // Sun Sep 13, 8:20 PM ET
const MNF = Date.UTC(2026, 8, 15, 0, 15); // Mon Sep 14, 8:15 PM ET

const iso = (ms: number) => new Date(ms).toISOString();
const gameId = (week: number, away: string, home: string) =>
  `${SEASON}_${String(week).padStart(2, "0")}_${away}_${home}`;

interface Week1Spec {
  away: string;
  home: string;
  kickoff: number;
  primetime?: boolean;
  homeProb: number | null; // null => prediction pending
  odds: Odds | null;
  weather: Weather | null; // null for domes
  factors: Factor[];
  narrative: string | null;
}

const f = (label: string, value: number, direction: "home" | "away"): Factor => ({
  label,
  value,
  direction,
});

const WEEK1: Week1Spec[] = [
  {
    away: "BUF",
    home: "KC",
    kickoff: THU,
    primetime: true,
    homeProb: 0.58,
    odds: { spread_home: -2.5, moneyline_home: -140, moneyline_away: 120, total: 48.5 },
    weather: { temp_f: 71, wind_mph: 8, precipitation: false, conditions: "Clear" },
    factors: [
      f("Elo rating edge", 0.11, "home"),
      f("Home field, opening-night crowd", 0.08, "home"),
      f("Offensive EPA/play, last 5 games", 0.06, "away"),
      f("Vegas market lean", 0.05, "home"),
    ],
    narrative:
      "Folks, the banner drops at Arrowhead and the model likes the home team at 58 percent! Kansas City brings the sharper rating edge and a Thursday-night crowd that is worth real points, with the market laying 2.5 right alongside it. Buffalo's offense actually owns the better recent EPA per play, so if the Bills steal an early possession, this one tightens in a hurry.",
  },
  {
    away: "CIN",
    home: "CLE",
    kickoff: SUN_EARLY,
    homeProb: 0.41,
    odds: { spread_home: 2.5, moneyline_home: 115, moneyline_away: -135, total: 44.5 },
    weather: { temp_f: 66, wind_mph: 12, precipitation: false, conditions: "Partly cloudy" },
    factors: [
      f("Offensive EPA/play, last 5 games", 0.12, "away"),
      f("Elo rating edge", 0.07, "away"),
      f("Home field", 0.06, "home"),
      f("Divisional familiarity", 0.03, "home"),
    ],
    narrative:
      "The Bengals stroll into the Dawg Pound as 59-percent road favorites, and the biggest number on the board is Cincinnati's passing-game efficiency over its last five. Cleveland counters with the home crowd, a 12-mile-an-hour lake breeze, and all the ugly familiarity of an AFC North opener. The model says that closes some of the gap — just not the 2.5 points of it that Vegas is asking.",
  },
  {
    away: "NE",
    home: "MIA",
    kickoff: SUN_EARLY,
    homeProb: 0.55,
    odds: { spread_home: -1.5, moneyline_home: -125, moneyline_away: 105, total: 43.5 },
    weather: { temp_f: 88, wind_mph: 12, precipitation: false, conditions: "Sunny" },
    factors: [
      f("Home field, early-September heat", 0.09, "home"),
      f("Point differential, last 5 games", 0.05, "home"),
      f("Turnover margin, last 3 games", 0.04, "away"),
    ],
    narrative:
      "It is 88 degrees and swampy in Miami Gardens, and history says that September sun is worth something real — the model hands the Dolphins 55 percent, with the heat-soaked home edge leading the story. New England's ball security has been the cleaner act lately, so the Patriots' path is simple: no free possessions, keep it a one-score game into the fourth.",
  },
  {
    away: "JAX",
    home: "IND",
    kickoff: SUN_EARLY,
    homeProb: 0.52,
    odds: { spread_home: -1, moneyline_home: -115, moneyline_away: -105, total: 45.5 },
    weather: null,
    factors: [
      f("Home field, indoors", 0.05, "home"),
      f("Elo rating edge", 0.03, "away"),
      f("Win percentage, last 5 games", 0.02, "home"),
    ],
    narrative:
      "Under the roof at Lucas Oil this one is a genuine coin flip with a home-field thumb on the scale — Indianapolis at 52 percent, laying a single point. Jacksonville actually grades out a hair better by rating, so if you like road divisional dogs, the model says this is the least you'll ever pay for one.",
  },
  {
    away: "MIN",
    home: "CHI",
    kickoff: SUN_EARLY,
    homeProb: 0.47,
    odds: { spread_home: 1.5, moneyline_home: 105, moneyline_away: -125, total: 42.5 },
    weather: { temp_f: 69, wind_mph: 14, precipitation: false, conditions: "Windy" },
    factors: [
      f("Defensive EPA/play, last 5 games", 0.08, "away"),
      f("Home field", 0.06, "home"),
      f("Wind at kickoff", 0.03, "home"),
    ],
    narrative:
      "Fourteen-mile-an-hour gusts off the lake at Soldier Field, and that wind is quietly a Bears ally — it drags Minnesota's downfield passing game back toward the pack. Still, the Vikings' defense has been the best unit on either roster over the last five, and the model makes them a slim 53-percent road favorite in a game Vegas has at a field goal and a hook... err, a point and a half.",
  },
  {
    away: "NO",
    home: "ATL",
    kickoff: SUN_EARLY,
    homeProb: 0.61,
    odds: { spread_home: -3.5, moneyline_home: -170, moneyline_away: 150, total: 46.5 },
    weather: null,
    factors: [
      f("Elo rating edge", 0.1, "home"),
      f("Offensive EPA/play, last 5 games", 0.07, "home"),
      f("Home field, indoors", 0.05, "home"),
      f("Divisional familiarity", 0.02, "away"),
    ],
    narrative:
      "The lights come up in Mercedes-Benz and the model comes out swinging: Atlanta at 61 percent, the cleanest rating edge of the early window. The Falcons' offense has been humming indoors, and the fast track only amplifies it. New Orleans' best card is forty years of NFC South spite — divisional dogs bite more often than the spread suggests.",
  },
  {
    away: "CAR",
    home: "TB",
    kickoff: SUN_EARLY,
    homeProb: 0.64,
    odds: { spread_home: -4.5, moneyline_home: -200, moneyline_away: 175, total: 45.5 },
    weather: { temp_f: 90, wind_mph: 9, precipitation: true, conditions: "Scattered storms" },
    factors: [
      f("Elo rating edge", 0.13, "home"),
      f("Win percentage, last 5 games", 0.07, "home"),
      f("Rain in the forecast", 0.03, "away"),
    ],
    narrative:
      "Tampa at 64 percent is the biggest home number of Week 1's early slate, built on a rating gap you could drive the pirate ship through. The wild card is weather — scattered storms and 90-degree soup tend to shorten games, and a shorter game is exactly what a Carolina underdog orders. The Bucs have won the recent-form battle going away; they just need to keep the ball dry.",
  },
  {
    away: "NYJ",
    home: "PIT",
    kickoff: SUN_EARLY,
    homeProb: 0.57,
    odds: { spread_home: -2.5, moneyline_home: -135, moneyline_away: 115, total: 41.5 },
    weather: { temp_f: 72, wind_mph: 7, precipitation: false, conditions: "Clear" },
    factors: [
      f("Defensive EPA/play, last 5 games", 0.09, "home"),
      f("Home field", 0.06, "home"),
      f("Turnover margin, last 3 games", 0.04, "away"),
    ],
    narrative:
      "Acrisure Stadium, black and gold everywhere, and a 41.5 total that tells you exactly what kind of afternoon this is — a rock fight! Pittsburgh's defense has been elite by EPA over the last five and that's the spine of a 57-percent home lean. The Jets' takeaway streak is the counterpunch: in a game this low-scoring, one short field can flip the whole script.",
  },
  {
    away: "WAS",
    home: "NYG",
    kickoff: SUN_EARLY,
    homeProb: 0.45,
    odds: { spread_home: 2, moneyline_home: 110, moneyline_away: -130, total: 44.5 },
    weather: { temp_f: 75, wind_mph: 10, precipitation: false, conditions: "Clear" },
    factors: [
      f("Offensive EPA/play, last 5 games", 0.1, "away"),
      f("Elo rating edge", 0.05, "away"),
      f("Home field", 0.06, "home"),
    ],
    narrative:
      "Washington marches into MetLife a 55-percent favorite, and it's the offense doing the talking — the Commanders' EPA per play over their last five laps the Giants' number. New York's whole case is the building and the rivalry; the model gives the home crowd its usual bump and not an ounce more. Two-point spread, division game, September in Jersey — buckle up.",
  },
  {
    away: "TEN",
    home: "DEN",
    kickoff: SUN_LATE,
    homeProb: 0.66,
    odds: { spread_home: -5.5, moneyline_home: -240, moneyline_away: 205, total: 43.5 },
    weather: { temp_f: 83, wind_mph: 6, precipitation: false, conditions: "Sunny" },
    factors: [
      f("Elo rating edge", 0.14, "home"),
      f("Home field, mile-high altitude", 0.08, "home"),
      f("Point differential, last 5 games", 0.06, "home"),
    ],
    narrative:
      "A mile above sea level, 83 and sunny, and the model's largest number of the week: Denver at 66 percent! The Broncos hold the biggest rating edge on the Week 1 board and the altitude bump on top of it — that's how you get to minus-5.5. Tennessee's hope is the oldest one in football: keep it close into the thin-air fourth quarter and let one bounce decide it.",
  },
  {
    away: "ARI",
    home: "SF",
    kickoff: SUN_LATE,
    homeProb: 0.62,
    odds: { spread_home: -3.5, moneyline_home: -175, moneyline_away: 155, total: 47.5 },
    weather: { temp_f: 78, wind_mph: 11, precipitation: false, conditions: "Clear" },
    factors: [
      f("Point differential, last 5 games", 0.1, "home"),
      f("Elo rating edge", 0.08, "home"),
      f("Divisional familiarity", 0.03, "away"),
    ],
    narrative:
      "Levi's Stadium, NFC West football, and the Niners open as 62-percent favorites on the strength of a point differential that's been lapping the division. Arizona's consolation prize is familiarity — these clubs know each other's audibles by heart, and that intimacy historically shaves a little off the favorite's edge. Three and a half is the number; the model says lay it.",
  },
  {
    away: "HOU",
    home: "LAC",
    kickoff: SUN_LATE,
    homeProb: 0.51,
    odds: { spread_home: -1, moneyline_home: -110, moneyline_away: -110, total: 46.5 },
    weather: null,
    factors: [
      f("Home field, indoors", 0.05, "home"),
      f("Defensive EPA/play, last 5 games", 0.04, "away"),
      f("Win percentage, last 5 games", 0.03, "home"),
    ],
    narrative: null,
  },
  {
    away: "PHI",
    home: "LAR",
    kickoff: SUN_LATE,
    homeProb: 0.49,
    odds: { spread_home: 1, moneyline_home: 100, moneyline_away: -120, total: 48.5 },
    weather: null,
    factors: [
      f("Elo rating edge", 0.07, "away"),
      f("Home field, indoors", 0.05, "home"),
      f("Offensive EPA/play, last 5 games", 0.03, "away"),
    ],
    narrative:
      "SoFi under the canopy, and the model has this one balanced on a razor: Philadelphia 51, Los Angeles 49. The Eagles carry the slightly better rating and the slightly better offense; the Rams carry the building. When the gap is this thin, the booth's honest answer is that a single red-zone stop decides it — enjoy the show.",
  },
  {
    away: "GB",
    home: "DAL",
    kickoff: SUN_LATE_2,
    homeProb: 0.48,
    odds: { spread_home: 1.5, moneyline_home: 105, moneyline_away: -125, total: 49.5 },
    weather: null,
    factors: [
      f("Offensive EPA/play, last 5 games", 0.08, "away"),
      f("Home field, indoors", 0.06, "home"),
      f("Elo rating edge", 0.04, "away"),
    ],
    narrative:
      "Jerry World gets the late-window spotlight and a 49.5 total that promises fireworks. Green Bay arrives a narrow 52-percent road favorite behind the hotter offense — the Packers' recent EPA per play simply outranks Dallas's. The Cowboys' rebuttal is eighty thousand friends and a fast roof; the model listens, nods, and still leans a point and a half toward the visitors.",
  },
  {
    away: "BAL",
    home: "DET",
    kickoff: SNF,
    primetime: true,
    homeProb: 0.54,
    odds: { spread_home: -1.5, moneyline_home: -130, moneyline_away: 110, total: 51.5 },
    weather: null,
    factors: [
      f("Offensive EPA/play, last 5 games", 0.09, "home"),
      f("Home field, primetime crowd", 0.07, "home"),
      f("Elo rating edge", 0.06, "away"),
      f("Point differential, last 5 games", 0.03, "away"),
    ],
    narrative:
      "Sunday night in Ford Field, a 51.5 total, and two of the loudest offenses in football — somebody pinch the booth! Detroit takes 54 percent on the strength of its recent offensive efficiency and a primetime home crowd that registers on seismographs. Baltimore still owns the better overall rating, which is exactly why the model calls this the most watchable coin-weighted flip of the week.",
  },
  {
    away: "SEA",
    home: "LV",
    kickoff: MNF,
    primetime: true,
    homeProb: null,
    odds: { spread_home: 1.5, moneyline_home: 105, moneyline_away: -125, total: 44.5 },
    weather: null,
    factors: [],
    narrative: null,
  },
];

// --- Builders ------------------------------------------------------------

function week1Games(): GameSummary[] {
  return WEEK1.map((s) => ({
    game_id: gameId(1, s.away, s.home),
    kickoff: iso(s.kickoff),
    home: { abbr: s.home, name: TEAMS[s.home].nickname },
    away: { abbr: s.away, name: TEAMS[s.away].nickname },
    is_primetime: !!s.primetime,
    status: "scheduled",
    has_prediction: s.homeProb !== null,
    home_win_prob: s.homeProb,
  }));
}

/** Deterministic round-robin pairings for weeks 2–18 (schedule-only). */
function generatedWeekGames(week: number): GameSummary[] {
  const [fixed, ...rest] = TEAM_ABBRS;
  const shift = (week - 1) % rest.length;
  const rotated = [...rest.slice(shift), ...rest.slice(0, shift)];
  const order = [fixed, ...rotated];

  const base = THU + (week - 1) * WEEK_MS;
  const sunEarly = SUN_EARLY + (week - 1) * WEEK_MS;
  const sunLate = SUN_LATE_2 + (week - 1) * WEEK_MS;
  const snf = SNF + (week - 1) * WEEK_MS;
  const mnf = MNF + (week - 1) * WEEK_MS;

  const games: GameSummary[] = [];
  for (let i = 0; i < 16; i++) {
    const a = order[i];
    const b = order[order.length - 1 - i];
    const [away, home] = week % 2 === 0 ? [a, b] : [b, a];
    let kickoff = sunEarly;
    let primetime = false;
    if (i === 0) {
      kickoff = base;
      primetime = true;
    } else if (i === 14) {
      kickoff = snf;
      primetime = true;
    } else if (i === 15) {
      kickoff = mnf;
      primetime = true;
    } else if (i >= 10) {
      kickoff = sunLate;
    }
    games.push({
      game_id: gameId(week, away, home),
      kickoff: iso(kickoff),
      home: { abbr: home, name: TEAMS[home].nickname },
      away: { abbr: away, name: TEAMS[away].nickname },
      is_primetime: primetime,
      status: "scheduled",
      has_prediction: false,
      home_win_prob: null,
    });
  }
  games.sort((x, y) => x.kickoff.localeCompare(y.kickoff));
  return games;
}

export function mockTeams(): Team[] {
  return TEAM_ABBRS.map((abbr, i) => {
    const m = TEAMS[abbr];
    return {
      id: i + 1,
      abbr,
      name: `${m.location} ${m.nickname}`,
      conference: m.conference,
      division: `${m.conference} ${m.division}`,
      logo_url: logoUrl(abbr),
    };
  });
}

export function mockSchedule(): Schedule {
  const weeks = [{ week: 1, games: week1Games() }];
  for (let w = 2; w <= 18; w++) weeks.push({ week: w, games: generatedWeekGames(w) });
  return { season: SEASON, weeks };
}

export function mockGames(week: number): GameSummary[] {
  if (week === 1) return week1Games();
  if (week >= 2 && week <= 18) return generatedWeekGames(week);
  return [];
}

export function mockMatchup(id: string): MatchupDetail | null {
  const spec = WEEK1.find((s) => gameId(1, s.away, s.home) === id);
  if (spec) {
    const home = TEAMS[spec.home];
    const ready = spec.homeProb !== null;
    return {
      game_id: id,
      season: SEASON,
      week: 1,
      kickoff: iso(spec.kickoff),
      venue: { name: home.stadium.name, city: home.stadium.city, is_dome: home.stadium.isDome },
      is_primetime: !!spec.primetime,
      is_divisional:
        TEAMS[spec.home].conference === TEAMS[spec.away].conference &&
        TEAMS[spec.home].division === TEAMS[spec.away].division,
      home: {
        abbr: spec.home,
        name: home.nickname,
        record: "0-0",
        logo_url: logoUrl(spec.home),
        win_prob: spec.homeProb,
      },
      away: {
        abbr: spec.away,
        name: TEAMS[spec.away].nickname,
        record: "0-0",
        logo_url: logoUrl(spec.away),
        win_prob: spec.homeProb === null ? null : Math.round((1 - spec.homeProb) * 100) / 100,
      },
      odds: spec.odds,
      weather: spec.weather,
      factors: spec.factors,
      narrative: spec.narrative,
      model_version: ready ? "0.1.0" : null,
      predicted_at: ready ? iso(Date.UTC(2026, 8, 8, 12, 0)) : null,
      prediction_status: ready ? "ready" : "pending",
    };
  }

  // Generated weeks: return a "prediction pending" detail.
  for (let w = 2; w <= 18; w++) {
    const g = generatedWeekGames(w).find((x) => x.game_id === id);
    if (!g) continue;
    const home = TEAMS[g.home.abbr];
    const away = TEAMS[g.away.abbr];
    return {
      game_id: id,
      season: SEASON,
      week: w,
      kickoff: g.kickoff,
      venue: { name: home.stadium.name, city: home.stadium.city, is_dome: home.stadium.isDome },
      is_primetime: g.is_primetime,
      is_divisional: home.conference === away.conference && home.division === away.division,
      home: { abbr: g.home.abbr, name: home.nickname, record: "0-0", logo_url: logoUrl(g.home.abbr), win_prob: null },
      away: { abbr: g.away.abbr, name: away.nickname, record: "0-0", logo_url: logoUrl(g.away.abbr), win_prob: null },
      odds: null,
      weather: null,
      factors: [],
      narrative: null,
      model_version: null,
      predicted_at: null,
      prediction_status: "pending",
    };
  }
  return null;
}
