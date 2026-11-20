// TypeScript mirror of the backend API contract.

export type Sport = "NFL" | "CFB";

export type SeasonType = "regular" | "postseason";

/** Mirrors backend app/postseason.py ROUNDS. */
export type Round =
  | "conf_championship"
  | "wild_card"
  | "divisional"
  | "conference"
  | "super_bowl"
  | "bowl"
  | "cfp_first_round"
  | "cfp_quarterfinal"
  | "cfp_semifinal"
  | "cfp_championship"
  | "cfp_other";

/** Postseason identity shared by GameSummary and MatchupDetail. */
export interface Occasion {
  season_type: SeasonType;
  round: Round | null;
  /** Display name, e.g. "Rose Bowl, CFP Quarterfinal" or "Super Bowl LXI". */
  event_name: string | null;
  /** CFP seeds only; null everywhere else. */
  home_seed: number | null;
  away_seed: number | null;
}

export interface Team {
  id: number;
  abbr: string;
  name: string;
  conference: string;
  division: string | null;
  logo_url: string | null;
  sport?: Sport;
  tier?: "FBS" | "FCS" | null;
  color?: string | null;
  alt_color?: string | null;
}

export interface GameTeamRef {
  abbr: string;
  name: string;
  rank?: number | null; // AP rank entering the game's week; null/absent = unranked
  conference?: string | null;
  logo_url?: string | null;
  color?: string | null;
}

export interface GameSummary extends Occasion {
  game_id: string;
  kickoff: string | null; // ISO-8601 UTC; null = kickoff TBD
  home: GameTeamRef;
  away: GameTeamRef;
  is_primetime: boolean;
  status: string;
  has_prediction: boolean;
  sport?: Sport;
  /** Frontend extension: compact win-prob hint for cards. Optional — the
   *  card degrades to a "prediction ready" state when absent. */
  home_win_prob?: number | null;
  /** De-vigged market win probability for the home team; null when no
   *  market data is available for this game. */
  market_home_prob: number | null;
  home_score: number | null;
  away_score: number | null;
  prediction_correct: boolean | null;
  is_neutral_site: boolean;
}

/** One chip on the week strip: a regular week ("w14") or a postseason round ("bowls"). */
export interface Slate {
  key: string;
  phase: SeasonType;
  week: number;
  round: Round | null;
  label: string | null;
  group_label: string;
  short_label: string;
  game_count: number;
  first_kickoff: string | null;
  next_kickoff: string | null;
  has_unscheduled: boolean;
  last_kickoff: string | null;
}

// Mirrors the backend's RecordOut. `sport` is null when a record spans both
// sports (not currently exposed by the UI, but the field is nullable there).
export interface Record {
  sport: string | null;
  season: number;
  correct: number;
  total: number;
  market_correct: number;
  sufficient: boolean;
}

export interface ScheduleWeek {
  week: number;
  games: GameSummary[];
}

export interface Schedule {
  season: number;
  weeks: ScheduleWeek[];
  sport?: Sport;
}

export interface PredictionTeam {
  abbr: string;
  name: string;
  record: string;
  logo_url: string | null;
  win_prob: number | null;
  rank?: number | null;
  conference?: string | null;
  color?: string | null;
}

export interface Venue {
  // Null only if the source genuinely has no venue at all. Neutral-site
  // games (is_neutral_site true) still populate name from the raw venue
  // string; city/is_dome stay null since there's no Stadium row for most
  // international venues.
  name: string | null;
  city: string | null;
  is_dome: boolean | null;
  is_neutral_site: boolean;
}

// Any single market can be missing: nflverse often carries a spread with no
// moneyline, so the container is present while members are null.
export interface Odds {
  spread_home: number | null;
  moneyline_home: number | null;
  moneyline_away: number | null;
  total: number | null;
}

export interface Weather {
  temp_f: number | null;
  wind_mph: number | null;
  precipitation: boolean | null;
  conditions: string | null;
}

export interface Factor {
  label: string;
  value: number;
  direction: "home" | "away";
}

export type PredictionStatus = "ready" | "pending";

export interface MatchupDetail extends Occasion {
  game_id: string;
  season: number;
  week: number;
  kickoff: string | null;
  venue: Venue;
  is_primetime: boolean;
  is_divisional: boolean;
  home: PredictionTeam;
  away: PredictionTeam;
  odds: Odds | null;
  weather: Weather | null;
  factors: Factor[];
  narrative: string | null;
  model_version: string | null;
  predicted_at: string | null;
  prediction_status: PredictionStatus;
  sport?: Sport;
  home_score: number | null;
  away_score: number | null;
  prediction_correct: boolean | null;
}
