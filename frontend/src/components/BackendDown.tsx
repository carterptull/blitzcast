import Link from "next/link";

/** Friendly full-page state when the API is unreachable in non-mock mode. */
export default function BackendDown() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <section className="turf overflow-hidden rounded-2xl">
        <div className="flex flex-col items-center px-6 py-16 text-center sm:py-24">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-gold-turf">
            Delay of game
          </span>
          <h1 className="mt-3 font-display text-4xl uppercase leading-tight tracking-wide text-chalk sm:text-5xl">
            We can&apos;t reach the press box
          </h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-chalk-soft">
            The Blitzcast API isn&apos;t answering. If you&apos;re running locally, make sure the
            backend is up — or set <code className="font-mono text-chalk">NEXT_PUBLIC_USE_MOCK=1</code>{" "}
            to browse the demo slate.
          </p>
          <Link
            href="/"
            className="mt-8 rounded-full border border-gold-turf px-5 py-2 font-mono text-xs uppercase tracking-[0.18em] text-gold-turf transition-colors hover:bg-gold-turf hover:text-[#10241c]"
          >
            Try again
          </Link>
        </div>
      </section>
    </div>
  );
}
