// URL sport segment ↔ API sport value mapping (CFB_IMPLEMENTATION_PLAN.md §5.1).

import type { Sport } from "./types";

export const SPORT_SLUGS = ["nfl", "cfb"] as const;
export type SportSlug = (typeof SPORT_SLUGS)[number];

export function isSportSlug(s: string): s is SportSlug {
  return (SPORT_SLUGS as readonly string[]).includes(s);
}

export function apiSport(slug: SportSlug): Sport {
  return slug === "cfb" ? "CFB" : "NFL";
}
