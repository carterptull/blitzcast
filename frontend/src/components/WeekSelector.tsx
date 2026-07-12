"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

interface Props {
  weeks: number[];
  selected: number;
  /** Sport slate path the week links point at, e.g. "/nfl". */
  basePath: string;
  /** Extra query params to preserve across week changes, e.g. "&conf=SEC". */
  query?: string;
}

export default function WeekSelector({ weeks, selected, basePath, query = "" }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>('[aria-current="page"]');
    el?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [selected]);

  return (
    <nav ref={ref} aria-label="Select week" className="no-scrollbar -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex w-max gap-2 py-1">
        {weeks.map((w) => {
          const active = w === selected;
          return (
            <li key={w}>
              <Link
                href={`${basePath}?week=${w}${query}`}
                scroll={false}
                aria-current={active ? "page" : undefined}
                className={`flex min-w-[3.25rem] flex-col items-center rounded-lg border px-3 py-1.5 transition-colors ${
                  active
                    ? "border-gold bg-stripe-a text-chalk"
                    : "border-edge bg-surface text-ink-soft hover:border-gold/50 hover:text-ink"
                }`}
              >
                <span className="font-mono text-[9px] uppercase tracking-[0.18em]">Wk</span>
                <span
                  className={`font-display text-lg leading-none tabular-nums ${active ? "text-gold-turf" : ""}`}
                >
                  {w}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
