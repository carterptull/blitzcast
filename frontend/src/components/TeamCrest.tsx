"use client";

import Image from "next/image";
import { useState } from "react";
import { displayAbbr, logoUrl, NEUTRAL_PRIMARY, TEAMS, textOn } from "@/lib/teams";

interface Props {
  abbr: string;
  size?: number;
  className?: string;
  /** Explicit logo source (CFB). When provided — even as null — the static
   *  NFL map is bypassed entirely. */
  logoUrl?: string | null;
  label?: string;
  color?: string | null;
}

/** Team logo (ESPN CDN for NFL, API-supplied for CFB), falling back to a
 *  team-color monogram. */
export default function TeamCrest({
  abbr,
  size = 64,
  className = "",
  logoUrl: explicitSrc,
  label,
  color,
}: Props) {
  const [failed, setFailed] = useState(false);
  const explicit = explicitSrc !== undefined;
  const meta = explicit ? undefined : TEAMS[abbr];
  const src = explicit ? explicitSrc : meta ? logoUrl(abbr) : null;
  const name = label ?? (meta ? `${meta.location} ${meta.nickname}` : abbr);

  if (failed || !src) {
    const bg = (explicit ? color : meta?.primary) || NEUTRAL_PRIMARY;
    return (
      <span
        role="img"
        aria-label={name}
        className={`grid shrink-0 place-items-center rounded-full font-display ${className}`}
        style={{
          width: size,
          height: size,
          background: bg,
          color: textOn(bg),
          fontSize: size * (abbr.length > 3 ? 0.24 : 0.32),
          boxShadow: "inset 0 0 0 2px rgba(255,255,255,0.18)",
        }}
      >
        {explicit ? abbr : displayAbbr(abbr)}
      </span>
    );
  }

  return (
    <Image
      src={src}
      alt={`${name} logo`}
      width={size}
      height={size}
      unoptimized
      className={`shrink-0 object-contain drop-shadow-sm ${className}`}
      onError={() => setFailed(true)}
    />
  );
}
