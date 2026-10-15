import Link from "next/link";
import pkg from "../../package.json";

const beerUrl = process.env.NEXT_PUBLIC_BUYMEACOFFEE_URL;
const issuesUrl = "https://github.com/carterptull/blitzcast/issues/new/choose";

export default function Footer() {
  return (
    <footer className="mt-16 border-t border-edge">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 sm:grid sm:grid-cols-[1fr_auto_1fr] sm:items-center sm:px-6">
        <div className="flex flex-col items-center gap-1 text-sm text-ink-soft sm:items-start sm:justify-self-start xl:flex-row xl:items-center xl:gap-x-2">
          <span>© 2026 Paymon Software</span>
          <span aria-hidden="true" className="hidden text-edge xl:inline">
            ·
          </span>
          <span className="flex items-center gap-x-2">
            <Link href="/how-it-works" className="underline decoration-edge underline-offset-2 hover:text-ink">
              How It Works
            </Link>
            <span aria-hidden="true" className="text-edge">
              ·
            </span>
            <a
              href={issuesUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-edge underline-offset-2 hover:text-ink"
            >
              Report an Issue
            </a>
          </span>
        </div>
        <div className="sm:justify-self-center">
          {beerUrl ? (
            <a
              href={beerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-gold/60 px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-gold-text transition-colors hover:bg-gold hover:text-[#10241c]"
            >
              <span aria-hidden="true">🍺</span> Buy Me a Beer
            </a>
          ) : null}
        </div>
        <p className="font-mono text-xs tabular-nums text-ink-soft sm:justify-self-end">v{pkg.version}</p>
      </div>
    </footer>
  );
}
