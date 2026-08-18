"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

const TABS = [
  { slug: "nfl", label: "NFL" },
  { slug: "cfb", label: "CFB" },
] as const;

export default function Header() {
  const pathname = usePathname();
  const sport = pathname.startsWith("/cfb") ? "cfb" : "nfl";

  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:gap-4 sm:px-6">
        <Link href={`/${sport}`} className="group flex items-baseline gap-2 rounded-sm">
          {/* Kicking-tee mark */}
          <svg
            viewBox="0 0 12 12"
            className="size-2.5 self-center text-gold transition-transform group-hover:-rotate-12"
            aria-hidden="true"
          >
            <path d="M6 0 12 12 0 12z" fill="currentColor" />
          </svg>
          <span className="font-display text-2xl uppercase leading-none tracking-wide">
            Blitzcast
          </span>
          <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-ink-soft sm:inline">
            2026 Season
          </span>
        </Link>

        <div className="flex items-center gap-2 sm:gap-3">
          <nav aria-label="Sport" className="flex rounded-lg border border-edge bg-surface p-0.5">
            {TABS.map((t) => {
              const active = t.slug === sport;
              return (
                <Link
                  key={t.slug}
                  href={`/${t.slug}`}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-md px-2.5 py-1 font-mono text-[11px] font-medium uppercase tracking-[0.18em] transition-colors sm:px-3 ${
                    active
                      ? "bg-stripe-a text-gold-turf"
                      : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </nav>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
