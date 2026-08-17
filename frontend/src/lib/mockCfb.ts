// CFB fixture data for NEXT_PUBLIC_USE_MOCK=1 — a believable 2026 Week 1
// slate across conferences (ranked marquee, FBS-vs-FCS, TBD kickoff), plus
// generated schedule-only weeks 2–15.

import type {
  Factor,
  GameSummary,
  GameTeamRef,
  MatchupDetail,
  Odds,
  PredictionTeam,
  Schedule,
  Team,
  Weather,
} from "./types";

const SEASON = 2026;
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
// Week 1 anchors (UTC; September ET is UTC-4). Labor Day weekend 2026.
const THU = Date.UTC(2026, 8, 4, 0, 0); // Thu Sep 3, 8:00 PM ET
const FRI = Date.UTC(2026, 8, 5, 1, 0); // Fri Sep 4, 9:00 PM ET
const SAT_NOON = Date.UTC(2026, 8, 5, 16, 0); // Sat Sep 5, 12:00 PM ET
const SAT_TWO = Date.UTC(2026, 8, 5, 18, 0); // 2:00 PM ET
const SAT_AFT = Date.UTC(2026, 8, 5, 19, 30); // 3:30 PM ET
const SAT_EVE = Date.UTC(2026, 8, 5, 23, 30); // 7:30 PM ET
const SAT_LATE = Date.UTC(2026, 8, 6, 2, 15); // 10:15 PM ET

const iso = (ms: number) => new Date(ms).toISOString();

interface CfbTeamMeta {
  name: string;
  conference: string;
  tier: "FBS" | "FCS";
  color: string | null;
  espnId: number | null; // null → monogram fallback
  stadium: { name: string; city: string };
}

const m = (
  name: string,
  conference: string,
  color: string | null,
  espnId: number | null,
  stadiumName: string,
  stadiumCity: string,
  tier: "FBS" | "FCS" = "FBS"
): CfbTeamMeta => ({ name, conference, tier, color, espnId, stadium: { name: stadiumName, city: stadiumCity } });

const CFB: Record<string, CfbTeamMeta> = {
  OSU: m("Ohio State Buckeyes", "Big Ten", "#BB0000", 194, "Ohio Stadium", "Columbus"),
  TEX: m("Texas Longhorns", "SEC", "#BF5700", 251, "DKR-Texas Memorial Stadium", "Austin"),
  ALA: m("Alabama Crimson Tide", "SEC", "#9E1B32", 333, "Bryant-Denny Stadium", "Tuscaloosa"),
  UGA: m("Georgia Bulldogs", "SEC", "#BA0C2F", 61, "Sanford Stadium", "Athens"),
  LSU: m("LSU Tigers", "SEC", "#461D7C", 99, "Tiger Stadium", "Baton Rouge"),
  ORE: m("Oregon Ducks", "Big Ten", "#154733", 2483, "Autzen Stadium", "Eugene"),
  UW: m("Washington Huskies", "Big Ten", "#4B2E83", 264, "Husky Stadium", "Seattle"),
  NEB: m("Nebraska Cornhuskers", "Big Ten", "#E41C38", 158, "Memorial Stadium", "Lincoln"),
  CLEM: m("Clemson Tigers", "ACC", "#F56600", 228, "Memorial Stadium", "Clemson"),
  MIA: m("Miami Hurricanes", "ACC", "#F47321", 2390, "Hard Rock Stadium", "Miami Gardens"),
  GT: m("Georgia Tech Yellow Jackets", "ACC", "#B3A369", 59, "Bobby Dodd Stadium", "Atlanta"),
  UNC: m("North Carolina Tar Heels", "ACC", "#7BAFD4", 153, "Kenan Stadium", "Chapel Hill"),
  ISU: m("Iowa State Cyclones", "Big 12", "#C8102E", 66, "Jack Trice Stadium", "Ames"),
  KSU: m("Kansas State Wildcats", "Big 12", "#512888", 2306, "Bill Snyder Family Stadium", "Manhattan"),
  TCU: m("TCU Horned Frogs", "Big 12", "#4D1979", 2628, "Amon G. Carter Stadium", "Fort Worth"),
  CIN: m("Cincinnati Bearcats", "Big 12", "#E00122", 2132, "Nippert Stadium", "Cincinnati"),
  ASU: m("Arizona State Sun Devils", "Big 12", "#8C1D40", 9, "Mountain America Stadium", "Tempe"),
  ND: m("Notre Dame Fighting Irish", "FBS Independents", "#0C2340", 87, "Notre Dame Stadium", "Notre Dame"),
  BSU: m("Boise State Broncos", "Mountain West", "#0033A0", 68, "Albertsons Stadium", "Boise"),
  FRES: m("Fresno State Bulldogs", "Mountain West", "#DB0032", 278, "Valley Children's Stadium", "Fresno"),
  USU: m("Utah State Aggies", "Mountain West", "#0F2439", 328, "Maverik Stadium", "Logan"),
  TUL: m("Tulane Green Wave", "American", "#006747", 2655, "Yulman Stadium", "New Orleans"),
  ECU: m("East Carolina Pirates", "American", "#592A8A", 151, "Dowdy-Ficklen Stadium", "Greenville"),
  // FCS guest with no color/logo — exercises the neutral monogram fallback.
  MER: m("Mercer Bears", "Southern", null, null, "Five Star Stadium", "Macon", "FCS"),
};

const CFB_ABBRS = Object.keys(CFB);

/** AP Top 25 entering Week 1 (fixture subset). */
const RANKS: Record<string, number> = {
  OSU: 1,
  TEX: 3,
  ALA: 4,
  UGA: 6,
  ORE: 7,
  LSU: 9,
  ND: 10,
  CLEM: 11,
  MIA: 14,
  ISU: 17,
  BSU: 19,
};

const cfbLogo = (id: number | null) =>
  id === null ? null : `https://a.espncdn.com/i/teamlogos/ncaa/500/${id}.png`;

function ref(abbr: string): GameTeamRef {
  const t = CFB[abbr];
  return {
    abbr,
    name: t.name,
    rank: RANKS[abbr] ?? null,
    conference: t.conference,
    logo_url: cfbLogo(t.espnId),
    color: t.color,
  };
}

interface Week1Spec {
  id: number;
  away: string;
  home: string;
  kickoff: number | null; // null => TBD
  primetime?: boolean;
  conferenceGame?: boolean;
  homeProb: number | null; // null => prediction pending
  odds: Odds | null;
  weather: Weather | null;
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
    id: 401520281,
    away: "CIN",
    home: "NEB",
    kickoff: THU,
    primetime: true,
    homeProb: 0.63,
    odds: { spread_home: 4.5, moneyline_home: -190, moneyline_away: 165, total: 51.5 },
    weather: { temp_f: 81, wind_mph: 9, precipitation: false, conditions: "Clear" },
    factors: [
      f("Elo rating edge", 0.12, "home"),
      f("Home field, sellout streak crowd", 0.08, "home"),
      f("Offensive PPA, last 5 games", 0.05, "away"),
    ],
    narrative: null,
  },
  {
    id: 401520282,
    away: "TCU",
    home: "UNC",
    kickoff: FRI,
    primetime: true,
    homeProb: 0.47,
    odds: { spread_home: -1.5, moneyline_home: 110, moneyline_away: -130, total: 55.5 },
    weather: { temp_f: 79, wind_mph: 6, precipitation: false, conditions: "Partly cloudy" },
    factors: [
      f("Offensive PPA, last 5 games", 0.09, "away"),
      f("Home field", 0.06, "home"),
      f("Elo rating edge", 0.04, "away"),
    ],
    narrative: null,
  },
  {
    id: 401520283,
    away: "TEX",
    home: "OSU",
    kickoff: SAT_NOON,
    homeProb: 0.55,
    odds: { spread_home: 2.5, moneyline_home: -135, moneyline_away: 115, total: 52.5 },
    weather: { temp_f: 78, wind_mph: 7, precipitation: false, conditions: "Sunny" },
    factors: [
      f("Elo rating edge", 0.09, "home"),
      f("Home field, 105,000 at the Shoe", 0.07, "home"),
      f("Offensive PPA, last 5 games", 0.06, "away"),
      f("AP poll standing edge", 0.04, "home"),
      f("Vegas market lean", 0.03, "home"),
    ],
    narrative:
      "Number one against number three, high noon in the Horseshoe, and the model calls it Ohio State at 55 percent! The Buckeyes bring the sharper rating and a hundred and five thousand of their closest friends, with the market laying 2.5 right beside them. Texas counters with the more explosive offense play-for-play, so if the Longhorns cash in an early red-zone trip, this heavyweight bout goes the distance.",
  },
  {
    id: 401520284,
    away: "KSU",
    home: "ISU",
    kickoff: SAT_NOON,
    conferenceGame: true,
    homeProb: 0.58,
    odds: { spread_home: 3, moneyline_home: -155, moneyline_away: 135, total: 47.5 },
    weather: { temp_f: 84, wind_mph: 13, precipitation: false, conditions: "Breezy" },
    factors: [
      f("Elo rating edge", 0.08, "home"),
      f("Home field", 0.06, "home"),
      f("AP poll standing edge", 0.04, "home"),
      f("Conference clash", 0.02, "away"),
    ],
    narrative:
      "Farmageddon opens the Big 12 slate in Ames, and the seventeenth-ranked Cyclones take 58 percent behind the better rating and a Jack Trice crowd that travels nowhere and misses nothing. Kansas State's card is familiarity (conference clashes run closer than the sheet says) and a 13-mile-an-hour prairie wind that turns long drives into arm wrestling.",
  },
  {
    id: 401520285,
    away: "MER",
    home: "ALA",
    kickoff: SAT_TWO,
    homeProb: 0.98,
    odds: { spread_home: 41.5, moneyline_home: -8000, moneyline_away: 2500, total: 53.5 },
    weather: { temp_f: 91, wind_mph: 5, precipitation: false, conditions: "Hot and sunny" },
    factors: [
      f("FBS-vs-FCS class edge", 0.31, "home"),
      f("Elo rating edge", 0.17, "home"),
      f("Home field", 0.04, "home"),
    ],
    narrative:
      "Bryant-Denny in the September broil, and the model isn't mincing words: Alabama at 98 percent over an FCS visitor. The class edge between divisions is the single loudest number on the board, and the Tide's rating gap only piles on. For Mercer, success is measured in quarters kept respectable, and in the check that clears on Monday.",
  },
  {
    id: 401520286,
    away: "GT",
    home: "UGA",
    kickoff: SAT_AFT,
    homeProb: 0.84,
    odds: { spread_home: 14.5, moneyline_home: -750, moneyline_away: 520, total: 49.5 },
    weather: { temp_f: 88, wind_mph: 6, precipitation: true, conditions: "Afternoon storms" },
    factors: [
      f("Elo rating edge", 0.16, "home"),
      f("AP poll standing edge", 0.08, "home"),
      f("Home field", 0.06, "home"),
    ],
    narrative: null,
  },
  {
    id: 401520287,
    away: "BSU",
    home: "UW",
    kickoff: SAT_AFT,
    homeProb: 0.52,
    odds: { spread_home: 1, moneyline_home: -115, moneyline_away: -105, total: 54.5 },
    weather: { temp_f: 71, wind_mph: 8, precipitation: false, conditions: "Clear" },
    factors: [
      f("Home field, Montlake on the lake", 0.06, "home"),
      f("AP poll standing edge", 0.05, "away"),
      f("Elo rating edge", 0.03, "home"),
    ],
    narrative:
      "A ranked Group-of-Five heavyweight walks into Husky Stadium and the model can barely pick a side: Washington 52, Boise State 48. The nineteenth-ranked Broncos carry the poll cachet; the Huskies carry the building and a hair of rating edge. One point on the sheet, one possession in real life. Appointment football.",
  },
  {
    id: 401520288,
    away: "ECU",
    home: "TUL",
    kickoff: SAT_AFT,
    conferenceGame: true,
    homeProb: 0.55,
    odds: { spread_home: 2, moneyline_home: -125, moneyline_away: 105, total: 50.5 },
    weather: { temp_f: 92, wind_mph: 10, precipitation: true, conditions: "Scattered storms" },
    factors: [
      f("Elo rating edge", 0.06, "home"),
      f("Home field", 0.05, "home"),
      f("Conference clash", 0.02, "away"),
    ],
    narrative: null,
  },
  {
    id: 401520289,
    away: "LSU",
    home: "CLEM",
    kickoff: SAT_EVE,
    primetime: true,
    homeProb: 0.51,
    odds: { spread_home: -1, moneyline_home: -110, moneyline_away: -110, total: 48.5 },
    weather: { temp_f: 82, wind_mph: 5, precipitation: false, conditions: "Clear" },
    factors: [
      f("Home field, Death Valley at night", 0.08, "home"),
      f("AP poll standing edge", 0.05, "away"),
      f("Elo rating edge", 0.04, "away"),
      f("Vegas market lean", 0.02, "home"),
    ],
    narrative:
      "Two top-eleven teams, one Death Valley, and a model split right down the middle: Clemson 51, LSU 49. The ninth-ranked Tigers of the bayou bring the better rating and the better poll standing, but Saturday night in Clemson is worth real probability, and it's nearly the whole home case. Pick 'em on the sheet, pick 'em in the machine. Somebody's season starts with a haymaker.",
  },
  {
    id: 401520290,
    away: "MIA",
    home: "ND",
    kickoff: SAT_EVE,
    primetime: true,
    homeProb: 0.57,
    odds: { spread_home: 3, moneyline_home: -150, moneyline_away: 130, total: 47.5 },
    weather: { temp_f: 74, wind_mph: 9, precipitation: false, conditions: "Clear" },
    factors: [
      f("Elo rating edge", 0.08, "home"),
      f("Home field, first night game of the fall", 0.07, "home"),
      f("AP poll standing edge", 0.03, "home"),
      f("Offensive PPA, last 5 games", 0.03, "away"),
    ],
    narrative: null,
  },
  {
    id: 401520291,
    away: "FRES",
    home: "ORE",
    kickoff: null, // TBD — network pick pending
    homeProb: 0.9,
    odds: { spread_home: 24.5, moneyline_home: -2200, moneyline_away: 1050, total: 55.5 },
    weather: null,
    factors: [
      f("Elo rating edge", 0.18, "home"),
      f("AP poll standing edge", 0.09, "home"),
      f("Home field", 0.06, "home"),
    ],
    narrative:
      "No kickoff time yet (the networks are still haggling), but the model has already made up its mind: Oregon at 90 percent, whatever hour the lights come on at Autzen. The seventh-ranked Ducks hold the biggest FBS-on-FBS rating gap of the opening weekend. Fresno State's path is turnovers, tempo, and a little chaos; the Ducks' path is showing up.",
  },
  {
    id: 401520292,
    away: "USU",
    home: "ASU",
    kickoff: SAT_LATE,
    homeProb: null,
    odds: { spread_home: 10.5, moneyline_home: -420, moneyline_away: 330, total: 53.5 },
    weather: null,
    factors: [],
    narrative: null,
  },
];

// --- Builders ------------------------------------------------------------

function toSummary(s: Week1Spec): GameSummary {
  return {
    game_id: `cfb_${s.id}`,
    kickoff: s.kickoff === null ? null : iso(s.kickoff),
    home: ref(s.home),
    away: ref(s.away),
    is_primetime: !!s.primetime,
    status: "scheduled",
    has_prediction: s.homeProb !== null,
    sport: "CFB",
    home_win_prob: s.homeProb,
  };
}

/** Deterministic round-robin pairings for weeks 2–15 (schedule-only). */
function generatedWeekGames(week: number): GameSummary[] {
  const [fixed, ...rest] = CFB_ABBRS;
  const shift = (week - 1) % rest.length;
  const rotated = [...rest.slice(shift), ...rest.slice(0, shift)];
  const order = [fixed, ...rotated];
  const offset = (week - 1) * WEEK_MS;

  const games: GameSummary[] = [];
  for (let i = 0; i < 12; i++) {
    const a = order[i];
    const b = order[order.length - 1 - i];
    const [away, home] = week % 2 === 0 ? [a, b] : [b, a];
    let kickoff: number | null = SAT_NOON + offset;
    let primetime = false;
    if (i === 0) {
      kickoff = THU + offset;
      primetime = true;
    } else if (i === 1) {
      kickoff = FRI + offset;
      primetime = true;
    } else if (i === 11) {
      kickoff = null; // one TBD slot per week
    } else if (i >= 8) {
      kickoff = SAT_EVE + offset;
      primetime = i === 8;
    } else if (i >= 5) {
      kickoff = SAT_AFT + offset;
    }
    games.push({
      game_id: `cfb_${401520281 + week * 100 + i}`,
      kickoff: kickoff === null ? null : iso(kickoff),
      home: ref(home),
      away: ref(away),
      is_primetime: primetime,
      status: "scheduled",
      has_prediction: false,
      sport: "CFB",
      home_win_prob: null,
    });
  }
  games.sort((x, y) => (x.kickoff ?? "9999").localeCompare(y.kickoff ?? "9999"));
  return games;
}

export function cfbMockTeams(): Team[] {
  return CFB_ABBRS.map((abbr, i) => {
    const t = CFB[abbr];
    return {
      id: 100 + i,
      abbr,
      name: t.name,
      conference: t.conference,
      division: null,
      logo_url: cfbLogo(t.espnId),
      sport: "CFB",
      tier: t.tier,
      color: t.color,
      alt_color: null,
    };
  });
}

export function cfbMockGames(week: number): GameSummary[] {
  if (week === 1) return WEEK1.map(toSummary);
  if (week >= 2 && week <= 15) return generatedWeekGames(week);
  return [];
}

export function cfbMockSchedule(): Schedule {
  const weeks = [];
  for (let w = 1; w <= 15; w++) weeks.push({ week: w, games: cfbMockGames(w) });
  return { season: SEASON, weeks, sport: "CFB" };
}

function predTeam(abbr: string, winProb: number | null): PredictionTeam {
  const t = CFB[abbr];
  return {
    abbr,
    name: t.name,
    record: "0-0",
    logo_url: cfbLogo(t.espnId),
    win_prob: winProb,
    rank: RANKS[abbr] ?? null,
    conference: t.conference,
    color: t.color,
  };
}

export function cfbMockMatchup(id: string): MatchupDetail | null {
  const spec = WEEK1.find((s) => `cfb_${s.id}` === id);
  if (spec) {
    const home = CFB[spec.home];
    const ready = spec.homeProb !== null;
    return {
      game_id: id,
      season: SEASON,
      week: 1,
      kickoff: spec.kickoff === null ? null : iso(spec.kickoff),
      venue: { name: home.stadium.name, city: home.stadium.city, is_dome: false },
      is_primetime: !!spec.primetime,
      is_divisional: !!spec.conferenceGame,
      home: predTeam(spec.home, spec.homeProb),
      away: predTeam(
        spec.away,
        spec.homeProb === null ? null : Math.round((1 - spec.homeProb) * 100) / 100
      ),
      odds: spec.odds,
      weather: spec.weather,
      factors: spec.factors,
      narrative: spec.narrative,
      model_version: ready ? "cfb-0.1.0" : null,
      predicted_at: ready ? iso(Date.UTC(2026, 8, 1, 12, 0)) : null,
      prediction_status: ready ? "ready" : "pending",
      sport: "CFB",
    };
  }

  // Generated weeks: return a "prediction pending" detail.
  for (let w = 2; w <= 15; w++) {
    const g = generatedWeekGames(w).find((x) => x.game_id === id);
    if (!g) continue;
    const home = CFB[g.home.abbr];
    return {
      game_id: id,
      season: SEASON,
      week: w,
      kickoff: g.kickoff,
      venue: { name: home.stadium.name, city: home.stadium.city, is_dome: false },
      is_primetime: g.is_primetime,
      is_divisional: CFB[g.home.abbr].conference === CFB[g.away.abbr].conference,
      home: predTeam(g.home.abbr, null),
      away: predTeam(g.away.abbr, null),
      odds: null,
      weather: null,
      factors: [],
      narrative: null,
      model_version: null,
      predicted_at: null,
      prediction_status: "pending",
      sport: "CFB",
    };
  }
  return null;
}
