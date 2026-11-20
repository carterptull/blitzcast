"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { slateHref } from "@/lib/format";
import type { Slate } from "@/lib/types";

interface Props {
  slates: Slate[];
  selectedKey: string;
  /** Sport slate path the chips point at, e.g. "/nfl". */
  basePath: string;
  /** Extra query params to preserve across slate changes, e.g. "&conf=SEC". */
  query?: string;
}

export default function SlateSelector({ slates, selectedKey, basePath, query = "" }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>('[aria-current="page"]');
    el?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [selectedKey]);

  return (
    <nav ref={ref} aria-label="Select slate" className="no-scrollbar -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex w-max gap-2 py-1">
        {slates.map((s) => {
          const active = s.key === selectedKey;
          return (
            <li key={s.key}>
              {/* prefetch off: every chip is visible at once, and letting
                  Next.js prefetch all of them on mount tripped Vercel's
                  automatic DDoS mitigation (a burst of near-simultaneous
                  requests from one client reads as an attack pattern). */}
              <Link
                href={slateHref(basePath, s, query)}
                scroll={false}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={`flex min-w-[3.25rem] flex-col items-center rounded-lg border px-3 py-1.5 transition-colors ${
                  active
                    ? "border-gold bg-stripe-a text-chalk"
                    : "border-edge bg-surface text-ink-soft hover:border-gold/50 hover:text-ink"
                }`}
              >
                <span className="font-mono text-[9px] uppercase tracking-[0.18em]">{s.group_label}</span>
                <span
                  className={`font-display text-lg leading-none tabular-nums ${active ? "text-gold-turf" : ""}`}
                >
                  {s.short_label}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
