// Static NFL team metadata: colors (used as data in the win-prob split),
// stadium info for mock fixtures, and ESPN CDN logo slugs.

export type Conference = "AFC" | "NFC";
export type Division = "East" | "North" | "South" | "West";

export interface TeamMeta {
  abbr: string;
  location: string;
  nickname: string;
  conference: Conference;
  division: Division;
  primary: string;
  secondary: string;
  espnSlug: string;
  stadium: { name: string; city: string; isDome: boolean };
}

const t = (
  abbr: string,
  location: string,
  nickname: string,
  conference: Conference,
  division: Division,
  primary: string,
  secondary: string,
  stadiumName: string,
  stadiumCity: string,
  isDome: boolean,
  espnSlug?: string
): TeamMeta => ({
  abbr,
  location,
  nickname,
  conference,
  division,
  primary,
  secondary,
  espnSlug: espnSlug ?? abbr.toLowerCase(),
  stadium: { name: stadiumName, city: stadiumCity, isDome },
});

export const TEAMS: Record<string, TeamMeta> = {
  ARI: t("ARI", "Arizona", "Cardinals", "NFC", "West", "#97233F", "#FFB612", "State Farm Stadium", "Glendale", true),
  ATL: t("ATL", "Atlanta", "Falcons", "NFC", "South", "#A71930", "#101820", "Mercedes-Benz Stadium", "Atlanta", true),
  BAL: t("BAL", "Baltimore", "Ravens", "AFC", "North", "#241773", "#9E7C0C", "M&T Bank Stadium", "Baltimore", false),
  BUF: t("BUF", "Buffalo", "Bills", "AFC", "East", "#00338D", "#C60C30", "Highmark Stadium", "Orchard Park", false),
  CAR: t("CAR", "Carolina", "Panthers", "NFC", "South", "#0085CA", "#101820", "Bank of America Stadium", "Charlotte", false),
  CHI: t("CHI", "Chicago", "Bears", "NFC", "North", "#0B162A", "#C83803", "Soldier Field", "Chicago", false),
  CIN: t("CIN", "Cincinnati", "Bengals", "AFC", "North", "#FB4F14", "#101820", "Paycor Stadium", "Cincinnati", false),
  CLE: t("CLE", "Cleveland", "Browns", "AFC", "North", "#311D00", "#FF3C00", "Huntington Bank Field", "Cleveland", false),
  DAL: t("DAL", "Dallas", "Cowboys", "NFC", "East", "#041E42", "#869397", "AT&T Stadium", "Arlington", true),
  DEN: t("DEN", "Denver", "Broncos", "AFC", "West", "#FB4F14", "#002244", "Empower Field at Mile High", "Denver", false),
  DET: t("DET", "Detroit", "Lions", "NFC", "North", "#0076B6", "#B0B7BC", "Ford Field", "Detroit", true),
  GB: t("GB", "Green Bay", "Packers", "NFC", "North", "#203731", "#FFB612", "Lambeau Field", "Green Bay", false),
  HOU: t("HOU", "Houston", "Texans", "AFC", "South", "#03202F", "#A71930", "NRG Stadium", "Houston", true),
  IND: t("IND", "Indianapolis", "Colts", "AFC", "South", "#002C5F", "#A2AAAD", "Lucas Oil Stadium", "Indianapolis", true),
  JAX: t("JAX", "Jacksonville", "Jaguars", "AFC", "South", "#006778", "#D7A22A", "EverBank Stadium", "Jacksonville", false),
  KC: t("KC", "Kansas City", "Chiefs", "AFC", "West", "#E31837", "#FFB81C", "GEHA Field at Arrowhead Stadium", "Kansas City", false),
  LAC: t("LAC", "Los Angeles", "Chargers", "AFC", "West", "#0080C6", "#FFC20E", "SoFi Stadium", "Inglewood", true),
  LAR: t("LAR", "Los Angeles", "Rams", "NFC", "West", "#003594", "#FFA300", "SoFi Stadium", "Inglewood", true),
  LV: t("LV", "Las Vegas", "Raiders", "AFC", "West", "#101820", "#A5ACAF", "Allegiant Stadium", "Las Vegas", true),
  MIA: t("MIA", "Miami", "Dolphins", "AFC", "East", "#008E97", "#FC4C02", "Hard Rock Stadium", "Miami Gardens", false),
  MIN: t("MIN", "Minnesota", "Vikings", "NFC", "North", "#4F2683", "#FFC62F", "U.S. Bank Stadium", "Minneapolis", true),
  NE: t("NE", "New England", "Patriots", "AFC", "East", "#002244", "#C60C30", "Gillette Stadium", "Foxborough", false),
  NO: t("NO", "New Orleans", "Saints", "NFC", "South", "#D3BC8D", "#101820", "Caesars Superdome", "New Orleans", true),
  NYG: t("NYG", "New York", "Giants", "NFC", "East", "#0B2265", "#A71930", "MetLife Stadium", "East Rutherford", false),
  NYJ: t("NYJ", "New York", "Jets", "AFC", "East", "#125740", "#101820", "MetLife Stadium", "East Rutherford", false),
  PHI: t("PHI", "Philadelphia", "Eagles", "NFC", "East", "#004C54", "#A5ACAA", "Lincoln Financial Field", "Philadelphia", false),
  PIT: t("PIT", "Pittsburgh", "Steelers", "AFC", "North", "#FFB612", "#101820", "Acrisure Stadium", "Pittsburgh", false),
  SEA: t("SEA", "Seattle", "Seahawks", "NFC", "West", "#002244", "#69BE28", "Lumen Field", "Seattle", false),
  SF: t("SF", "San Francisco", "49ers", "NFC", "West", "#AA0000", "#B3995D", "Levi's Stadium", "Santa Clara", false),
  TB: t("TB", "Tampa Bay", "Buccaneers", "NFC", "South", "#D50A0A", "#34302B", "Raymond James Stadium", "Tampa", false),
  TEN: t("TEN", "Tennessee", "Titans", "AFC", "South", "#0C2340", "#4B92DB", "Nissan Stadium", "Nashville", false),
  WAS: t("WAS", "Washington", "Commanders", "NFC", "East", "#5A1414", "#FFB612", "Northwest Stadium", "Landover", false, "wsh"),
};

export const TEAM_ABBRS = Object.keys(TEAMS);

export function logoUrl(abbr: string): string {
  const slug = TEAMS[abbr]?.espnSlug ?? abbr.toLowerCase();
  return `https://a.espncdn.com/i/teamlogos/nfl/500/${slug}.png`;
}

/** Readable text color (chalk or ink) for a given team-color background. */
export function textOn(hex: string): string {
  const n = parseInt(hex.replace("#", ""), 16);
  const yiq = (((n >> 16) & 255) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000;
  return yiq >= 140 ? "#10241c" : "#f3f7f0";
}
