import pkg from "../../package.json";

const beerUrl = process.env.NEXT_PUBLIC_BUYMEACOFFEE_URL;

export default function Footer() {
  return (
    <footer className="mt-16 border-t border-edge">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 sm:grid sm:grid-cols-3 sm:items-center sm:px-6">
        <p className="text-sm text-ink-soft sm:justify-self-start">© 2026 Paymon Software</p>
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
