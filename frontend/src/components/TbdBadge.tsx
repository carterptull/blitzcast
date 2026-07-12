/** Kickoff-time-TBD badge (shared NFL/CFB). `onTurf` swaps to chalk colors. */
export default function TbdBadge({ onTurf = false }: { onTurf?: boolean }) {
  const cls = onTurf
    ? "border-chalk-soft/50 text-chalk-soft"
    : "border-ink-soft/50 text-ink-soft";
  return (
    <span
      className={`rounded-sm border border-dashed px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.15em] ${cls}`}
    >
      Time TBD
    </span>
  );
}
