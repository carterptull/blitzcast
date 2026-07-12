// TypeScript mirror of the backend API contract (IMPLEMENTATION_PLAN.md §3.2,
// CFB_IMPLEMENTATION_PLAN.md §3.1).

export type Sport = "NFL" | "CFB";

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

export interface GameSummary {
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
  name: string;
  city: string;
  is_dome: boolean;
}

export interface Odds {
  spread_home: number;
  moneyline_home: number;
  moneyline_away: number;
  total: number;
}

export interface Weather {
  temp_f: number;
  wind_mph: number;
  precipitation: boolean;
  conditions: string;
}

export interface Factor {
  label: string;
  value: number;
  direction: "home" | "away";
}

export type PredictionStatus = "ready" | "pending";

export interface MatchupDetail {
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
}
