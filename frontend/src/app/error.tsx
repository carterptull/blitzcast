"use client";

/** Route-level error boundary. Catches anything the API client does not
 *  already turn into a NotFoundError or ApiUnreachableError. */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <section className="turf overflow-hidden rounded-2xl">
        <div className="flex flex-col items-center px-6 py-16 text-center sm:py-24">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-gold-turf">
            Fumble
          </span>
          <h1 className="mt-3 font-display text-4xl uppercase leading-tight tracking-wide text-chalk sm:text-5xl">
            Something broke down on our end
          </h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-chalk-soft">
            That one is on us, not you. Run the play again, and if it keeps happening the press
            box is probably having a rough series.
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-8 rounded-full border border-gold-turf px-5 py-2 font-mono text-xs uppercase tracking-[0.18em] text-gold-turf transition-colors hover:bg-gold-turf hover:text-[#10241c]"
          >
            Run it back
          </button>
        </div>
      </section>
    </div>
  );
}
