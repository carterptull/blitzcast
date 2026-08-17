import { fmtDate } from "@/lib/format";
import { displayAbbr } from "@/lib/teams";
import type { MatchupDetail } from "@/lib/types";
import FactorList from "./FactorList";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
      <span className="inline-block size-1.5 rounded-full bg-gold" aria-hidden="true" />
      {children}
    </h2>
  );
}

export default function ReasoningPanel({ matchup }: { matchup: MatchupDetail }) {
  const m = matchup;
  const pending = m.prediction_status !== "ready";
  const favored = m.home.win_prob !== null && m.home.win_prob >= 0.5 ? m.home : m.away;

  if (pending) {
    return (
      <section className="rounded-xl border border-edge bg-surface p-6 sm:p-8">
        <SectionLabel>From the booth</SectionLabel>
        <p className="mt-4 text-lg italic leading-relaxed text-ink-soft">
          The model hasn&apos;t weighed in on this one yet. Predictions are generated after the
          weekly data refresh — once the lines, injuries, and weather are in, the numbers and the
          call from the booth will land right here.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-edge bg-surface p-6 sm:p-8">
      <SectionLabel>From the booth</SectionLabel>

      {m.narrative ? (
        <p className="mt-4 text-lg leading-relaxed sm:text-xl">{m.narrative}</p>
      ) : (
        <p className="mt-4 italic leading-relaxed text-ink-soft">
          The broadcast feed dropped out for this one — but the numbers still tell the story below.
        </p>
      )}

      {m.factors.length > 0 ? (
        <div className="mt-8">
          <h3 className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
            Why the model leans {m.sport === "CFB" ? favored.abbr : displayAbbr(favored.abbr)}
          </h3>
          <div className="mt-4">
            <FactorList matchup={m} />
          </div>
        </div>
      ) : null}

      {m.model_version ? (
        <p className="mt-8 border-t border-edge pt-4 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-soft">
          Model v{m.model_version}
          {m.predicted_at ? ` · predicted ${fmtDate(m.predicted_at)}` : ""} · not betting advice
        </p>
      ) : null}
    </section>
  );
}
