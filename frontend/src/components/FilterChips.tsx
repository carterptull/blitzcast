"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

interface Props {
  conferences: string[];
  activeConf: string | null;
  top25: boolean;
  week: number;
  /** Extra query params to preserve across conf/top25 changes, e.g. "&status=final". */
  query?: string;
}

/** Conference + Top-25 filter chips for the CFB slate. Filter state lives in
 *  the URL query, so a filtered slate is shareable. Clicking an active chip
 *  clears it. */
export default function FilterChips({ conferences, activeConf, top25, week, query = "" }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>('[aria-current="true"]');
    el?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [activeConf, top25]);

  const href = (conf: string | null, top: boolean) =>
    `/cfb?week=${week}${conf ? `&conf=${encodeURIComponent(conf)}` : ""}${top ? "&top25=1" : ""}${query}`;

  const base =
    "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors";
  const off = "border-edge bg-surface text-ink-soft hover:border-gold/50 hover:text-ink";
  const on = "border-gold bg-stripe-a text-gold-turf";

  return (
    <nav
      ref={ref}
      aria-label="Filter games"
      className="no-scrollbar -mx-4 mt-3 overflow-x-auto px-4 sm:mx-0 sm:px-0"
    >
      <div className="flex w-max items-center gap-2 py-1">
        <Link
          href={href(activeConf, !top25)}
          scroll={false}
          aria-current={top25 ? "true" : undefined}
          className={`${base} ${top25 ? on : off}`}
        >
          <svg viewBox="0 0 12 12" className="size-2" aria-hidden="true">
            <path
              d="M6 0l1.8 3.9 4.2.7-3 2.8.8 4.1L6 9.5 2.2 11.5 3 7.4 0 4.6l4.2-.7z"
              fill="currentColor"
            />
          </svg>
          Top 25
        </Link>
        <span className="h-4 w-px shrink-0 bg-edge" aria-hidden="true" />
        <Link
          href={href(null, top25)}
          scroll={false}
          aria-current={!activeConf ? "true" : undefined}
          className={`${base} ${!activeConf ? on : off}`}
        >
          All conferences
        </Link>
        {conferences.map((c) => {
          const active = c === activeConf;
          return (
            <Link
              key={c}
              href={href(active ? null : c, top25)}
              scroll={false}
              aria-current={active ? "true" : undefined}
              className={`${base} ${active ? on : off}`}
            >
              {c}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
