import type { Record } from "@/lib/types";

// Minimum sample the backend requires before `sufficient` flips true. Not
// used for logic here (the backend already decided), just for copy.
const MIN_SAMPLE = 10;

/** Season-to-date accuracy, always shown next to the market's number.
 *  Never render the model's figure alone — see spec §10: a bare accuracy
 *  number reads as a claim the model can't back up on its own. */
export default function RecordBanner({ record }: { record: Record }) {
  const { correct, total, market_correct, sufficient } = record;

  if (!sufficient) {
    return (
      <section
        aria-label="Season record"
        className="mb-6 rounded-xl border border-edge bg-surface px-4 py-3 font-mono text-xs uppercase tracking-[0.14em] text-ink-soft"
      >
        Not enough games yet &middot; {total} of {MIN_SAMPLE} tracked so far
      </section>
    );
  }

  const modelPct = Math.round((correct / total) * 100);
  const marketPct = Math.round((market_correct / total) * 100);

  return (
    <section
      aria-label="Season record"
      className="mb-6 rounded-xl border border-edge bg-surface px-4 py-3 font-mono text-xs uppercase tracking-[0.14em] text-ink-soft"
    >
      Model {correct}/{total} ({modelPct}%) <span className="mx-2 text-edge">&middot;</span>{" "}
      Market {market_correct}/{total} ({marketPct}%)
    </section>
  );
}
