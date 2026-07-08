"use client";

import Image from "next/image";
import { useState } from "react";
import { logoUrl, TEAMS, textOn } from "@/lib/teams";

interface Props {
  abbr: string;
  size?: number;
  className?: string;
}

/** Team logo from the ESPN CDN, falling back to a team-color monogram. */
export default function TeamCrest({ abbr, size = 64, className = "" }: Props) {
  const [failed, setFailed] = useState(false);
  const meta = TEAMS[abbr];

  if (failed || !meta) {
    const bg = meta?.primary ?? "#4f6459";
    return (
      <span
        role="img"
        aria-label={meta ? `${meta.location} ${meta.nickname}` : abbr}
        className={`grid shrink-0 place-items-center rounded-full font-display ${className}`}
        style={{
          width: size,
          height: size,
          background: bg,
          color: textOn(bg),
          fontSize: size * 0.32,
          boxShadow: "inset 0 0 0 2px rgba(255,255,255,0.18)",
        }}
      >
        {abbr}
      </span>
    );
  }

  return (
    <Image
      src={logoUrl(abbr)}
      alt={`${meta.location} ${meta.nickname} logo`}
      width={size}
      height={size}
      unoptimized
      className={`shrink-0 object-contain drop-shadow-sm ${className}`}
      onError={() => setFailed(true)}
    />
  );
}
