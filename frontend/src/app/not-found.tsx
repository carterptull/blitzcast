import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <section className="turf overflow-hidden rounded-2xl">
        <div className="flex flex-col items-center px-6 py-16 text-center sm:py-24">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-gold-turf">
            Flag on the play
          </span>
          <h1 className="mt-3 font-display text-4xl uppercase leading-tight tracking-wide text-chalk sm:text-5xl">
            That matchup isn&apos;t on the schedule
          </h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-chalk-soft">
            No game found at this address. Check the link, or head back to the week&apos;s slate.
          </p>
          <Link
            href="/"
            className="mt-8 rounded-full border border-gold-turf px-5 py-2 font-mono text-xs uppercase tracking-[0.18em] text-gold-turf transition-colors hover:bg-gold-turf hover:text-[#10241c]"
          >
            Back to the slate
          </Link>
        </div>
      </section>
    </div>
  );
}
