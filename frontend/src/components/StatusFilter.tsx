"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { StatusFilterValue } from "@/lib/api";
import type { SportSlug } from "@/lib/sport";

interface Props {
  sport: SportSlug;
  active: StatusFilterValue;
  week: number;
  /** Extra query params to preserve across status changes, e.g. "&conf=SEC". */
  query?: string;
}

const CHIPS: { value: StatusFilterValue; label: string }[] = [
  { value: "all", label: "All" },
  { value: "final", label: "Completed" },
  { value: "upcoming", label: "Upcoming" },
];

/** Game-status filter chips (all / completed / upcoming), shared by the NFL
 *  and CFB slates. Filter state lives in the URL query, so a filtered slate
 *  is shareable. Sport-parameterized rather than an extension of
 *  `FilterChips`, which hardcodes the `/cfb` path and conference logic. */
export default function StatusFilter({ sport, active, week, query = "" }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>('[aria-current="true"]');
    el?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [active]);

  const href = (status: StatusFilterValue) =>
    `/${sport}?week=${week}${status !== "all" ? `&status=${status}` : ""}${query}`;

  const base =
    "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors";
  const off = "border-edge bg-surface text-ink-soft hover:border-gold/50 hover:text-ink";
  const on = "border-gold bg-stripe-a text-gold-turf";

  return (
    <nav
      ref={ref}
      aria-label="Filter by game status"
      className="no-scrollbar -mx-4 mt-3 overflow-x-auto px-4 sm:mx-0 sm:px-0"
    >
      <div className="flex w-max items-center gap-2 py-1">
        {CHIPS.map(({ value, label }) => {
          const isActive = value === active;
          return (
            <Link
              key={value}
              href={href(value)}
              scroll={false}
              aria-current={isActive ? "true" : undefined}
              className={`${base} ${isActive ? on : off}`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
