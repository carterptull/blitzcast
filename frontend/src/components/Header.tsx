import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

export default function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-baseline gap-2 rounded-sm">
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
        <ThemeToggle />
      </div>
    </header>
  );
}
