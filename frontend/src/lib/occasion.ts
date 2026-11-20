// Shared postseason constants. Mirrors backend app/postseason.py.

import type { Occasion, Round } from "./types";

export const ROUNDS: readonly Round[] = [
  "conf_championship",
  "wild_card",
  "divisional",
  "conference",
  "super_bowl",
  "bowl",
  "cfp_first_round",
  "cfp_quarterfinal",
  "cfp_semifinal",
  "cfp_championship",
  "cfp_other",
];

/** The occasion fields of an ordinary regular-season game. */
export const REGULAR_OCCASION: Occasion = {
  season_type: "regular",
  round: null,
  event_name: null,
  home_seed: null,
  away_seed: null,
};
