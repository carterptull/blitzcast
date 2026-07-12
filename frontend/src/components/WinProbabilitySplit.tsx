"use client";

import { useEffect, useState } from "react";
import { TEAMS } from "@/lib/teams";

interface Side {
  abbr: string;
  prob: number;
  /** Pre-resolved fill color (CFB); NFL callers omit it and use the static map. */
  color?: string;
}

interface Props {
  away: Side;
  home: Side;
  /** "lg" = matchup hero, "sm" = compact card hint */
  size?: "lg" | "sm";
}

/**
 * The two-color split bar: each team's primary color as the fill, a gold
 * marker at the split. Animates from 50/50 on mount; the CSS transition is
 * disabled under prefers-reduced-motion.
 */
export default function WinProbabilitySplit({ away, home, size = "lg" }: Props) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const awayPct = armed ? away.prob * 100 : 50;
  const homePct = 100 - awayPct;
  const awayColor = away.color ?? TEAMS[away.abbr]?.primary ?? "#4f6459";
  const homeColor = home.color ?? TEAMS[home.abbr]?.primary ?? "#4f6459";
  const h = size === "lg" ? "h-4 sm:h-5" : "h-1.5";

  return (
    <div
      role="img"
      aria-label={`Win probability: ${away.abbr} ${Math.round(away.prob * 100)}%, ${home.abbr} ${Math.round(home.prob * 100)}%`}
      className={`relative w-full overflow-hidden ${size === "lg" ? "rounded-md" : "rounded-full"}`}
      style={{ boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.14)" }}
    >
      <div className={`flex ${h}`}>
        <div
          className="transition-[width] duration-1000 ease-out motion-reduce:transition-none"
          style={{ width: `${awayPct}%`, background: awayColor }}
        />
        <div
          className="transition-[width] duration-1000 ease-out motion-reduce:transition-none"
          style={{ width: `${homePct}%`, background: homeColor }}
        />
      </div>
      {/* Gold marker at the split */}
      <div
        aria-hidden="true"
        className="absolute inset-y-0 w-[3px] -translate-x-1/2 bg-gold-turf transition-[left] duration-1000 ease-out motion-reduce:transition-none"
        style={{ left: `${awayPct}%` }}
      />
    </div>
  );
}
