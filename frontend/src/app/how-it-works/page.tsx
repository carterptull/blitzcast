import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "What the Blitzcast model actually looks at, the rule that keeps it honest, and how it stacks up against Vegas. No spin.",
};

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-soft">
      <span className="inline-block size-1.5 rounded-full bg-gold" aria-hidden="true" />
      {children}
    </h2>
  );
}

function Section({
  label,
  title,
  children,
}: {
  label: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-edge bg-surface p-6 sm:p-8">
      <SectionLabel>{label}</SectionLabel>
      <h3 className="mt-3 font-display text-2xl uppercase leading-tight tracking-wide sm:text-3xl">
        {title}
      </h3>
      <div className="mt-4 space-y-4 text-base leading-relaxed text-ink-soft sm:text-lg">
        {children}
      </div>
    </section>
  );
}

function BacktestTable({
  caption,
  rows,
}: {
  caption: string;
  rows: { season: string; games: number; modelBrier: string; vegasBrier: string; modelAcc: string; vegasAcc: string }[];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-edge">
      <table className="w-full min-w-[480px] border-collapse text-sm">
        <caption className="border-b border-edge bg-canvas px-3 py-2 text-left font-mono text-[11px] uppercase tracking-[0.15em] text-ink-soft">
          {caption}
        </caption>
        <thead>
          <tr className="border-b border-edge text-left font-mono text-[10px] uppercase tracking-[0.15em] text-ink-soft">
            <th className="px-3 py-2 font-medium">Season</th>
            <th className="px-3 py-2 font-medium">Games</th>
            <th className="px-3 py-2 font-medium">Model Brier</th>
            <th className="px-3 py-2 font-medium">Vegas Brier</th>
            <th className="px-3 py-2 font-medium">Model Acc</th>
            <th className="px-3 py-2 font-medium">Vegas Acc</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r) => (
            <tr key={r.season} className="border-b border-edge last:border-b-0">
              <td className="px-3 py-2">{r.season}</td>
              <td className="px-3 py-2">{r.games}</td>
              <td className="px-3 py-2">{r.modelBrier}</td>
              <td className="px-3 py-2">{r.vegasBrier}</td>
              <td className="px-3 py-2">{r.modelAcc}</td>
              <td className="px-3 py-2">{r.vegasAcc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <section className="turf overflow-hidden rounded-2xl">
        <div className="px-6 py-10 sm:px-10 sm:py-14">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-gold-turf">
            From the booth
          </p>
          <h1 className="mt-2 max-w-xl font-display text-4xl uppercase leading-[0.95] tracking-wide text-chalk sm:text-5xl">
            How this whole thing works
          </h1>
          <p className="mt-4 max-w-xl text-lg italic leading-relaxed text-chalk-soft">
            No black box, no secret sauce. Here&apos;s what the model sees, the rule that keeps it
            honest, and how it holds up against the toughest opponent in football: the market.
          </p>
        </div>
      </section>

      <div className="mt-8 space-y-6">
        <Section label="The inputs" title="What the model actually looks at">
          <p>
            Every prediction comes out of a trained XGBoost classifier, one number between 0 and
            100 percent, built from twenty features that fall into a few plain-English buckets:
          </p>
          <ul className="ml-5 list-disc space-y-2">
            <li>
              <span className="font-medium text-ink">Team strength.</span> An Elo rating for each
              team that updates after every game, the same idea chess uses to rank players.
            </li>
            <li>
              <span className="font-medium text-ink">Recent form.</span> Offensive and defensive
              efficiency (EPA per play) over each team&apos;s last several games, not season-long
              averages that miss a hot or cold streak.
            </li>
            <li>
              <span className="font-medium text-ink">Rest.</span> Days between games for each
              side, short weeks and byes included.
            </li>
            <li>
              <span className="font-medium text-ink">Injuries.</span> Who&apos;s banged up, weighted
              heavier when it&apos;s the quarterback.
            </li>
            <li>
              <span className="font-medium text-ink">Weather.</span> Temperature, wind, and
              precipitation at kickoff, dome games treated as a controlled environment.
            </li>
            <li>
              <span className="font-medium text-ink">The market itself.</span> The current
              spread and the market&apos;s own implied win probability are two of the twenty
              inputs. The model gets to see what Vegas thinks before it makes its own call, and
              it still doesn&apos;t beat the market outright. More on that below.
            </li>
          </ul>
          <p>
            Each prediction ships with the top factors that moved the number, in plain language
            and pointed at the team they favor, not a bare percentage you have to take on faith.
          </p>
        </Section>

        <Section label="The leakage rule" title="Nothing from the game leaks into the pick">
          <p>
            Every feature for a given matchup is built strictly from data available before that
            game&apos;s kickoff. Elo ratings, recent form, rest, injuries, all of it is a snapshot
            of the week before, never the week of. A prediction never gets to peek at a score,
            a stat line, or anything else from the game it&apos;s predicting.
          </p>
          <p>
            This sounds obvious until you&apos;ve seen how easy it is to get wrong by accident, a
            model that accidentally learns from data it shouldn&apos;t have seen looks brilliant in
            testing and falls apart the moment it has to call a real, unplayed game. It&apos;s
            enforced with a dedicated automated test, not just a coding habit, so it can&apos;t
            quietly regress as the pipeline changes.
          </p>
        </Section>

        <Section label="The LLM boundary" title="Claude calls the game, it doesn't call the winner">
          <p>
            The XGBoost model produces the win probability. SHAP explains which factors pushed it
            that direction and by how much. Claude&apos;s only job is to turn that probability and
            those factors into the 2 to 4 sentences of broadcast-style color you read on a
            matchup page.
          </p>
          <p>
            Claude never sees the raw game data and never touches the math. It gets the number and
            the factor list as fixed inputs and is guardrailed against changing or inventing
            either one. If narration ever fails or comes back looking off, the page falls back to
            showing the factor list plainly rather than letting a bad sentence stand in for the
            model&apos;s actual call.
          </p>
        </Section>

        <Section label="The scoreboard" title="How often the model is wrong, honestly">
          <p>
            Every model gets evaluated the same way real forecasters do: walk-forward by season,
            training only on seasons already played and then grading the next one, compared
            against the closing betting lines for those same games with the bookmaker&apos;s cut
            removed. That&apos;s a demanding bar. Closing lines are one of the hardest baselines to
            beat using only public data, and this site doesn&apos;t beat it.
          </p>
          <BacktestTable
            caption="NFL, walk-forward 2023 to 2025"
            rows={[
              { season: "2023", games: 285, modelBrier: "0.2415", vegasBrier: "0.2186", modelAcc: "60.4%", vegasAcc: "67.7%" },
              { season: "2024", games: 285, modelBrier: "0.2099", vegasBrier: "0.2010", modelAcc: "69.1%", vegasAcc: "70.5%" },
              { season: "2025", games: 285, modelBrier: "0.2173", vegasBrier: "0.2104", modelAcc: "65.6%", vegasAcc: "66.3%" },
              { season: "All", games: 855, modelBrier: "0.2229", vegasBrier: "0.2100", modelAcc: "65.0%", vegasAcc: "68.2%" },
            ]}
          />
          <p>
            College football gets its own model, its own Elo history, and its own backtest,
            graded against de-vigged closing lines from CFBD (FBS versus FBS games only, since
            the market barely prices FCS mismatches):
          </p>
          <BacktestTable
            caption="CFB, walk-forward 2023 to 2025"
            rows={[
              { season: "2023", games: 755, modelBrier: "0.1842", vegasBrier: "0.1685", modelAcc: "69.5%", vegasAcc: "73.9%" },
              { season: "2024", games: 757, modelBrier: "0.1844", vegasBrier: "0.1781", modelAcc: "71.7%", vegasAcc: "72.7%" },
              { season: "2025", games: 763, modelBrier: "0.1754", vegasBrier: "0.1719", modelAcc: "73.8%", vegasAcc: "74.8%" },
              { season: "All", games: 2275, modelBrier: "0.1813", vegasBrier: "0.1729", modelAcc: "71.7%", vegasAcc: "73.8%" },
            ]}
          />
          <p>
            Read straight: on the full sample, the NFL model calls the winner about 65.0 percent
            of the time against the market&apos;s 68.2 percent, a gap of roughly 3 points. CFB runs
            71.7 percent against 73.8 percent, about 2 points back. Brier score, which grades not
            just whether the pick was right but how confident the model was while making it,
            tells the same story: the market scores lower (better) than the model in every single
            season, both sports, no exceptions.
          </p>
          <p>
            None of that means the model is guessing. It lands in the neighborhood of a real
            sportsbook line using only public data, which is a genuinely hard thing to do. It just
            doesn&apos;t mean the model has an edge on Vegas, and this page isn&apos;t going to
            pretend otherwise. Every prediction on the site is labeled with a model version and a
            timestamp, and nothing here is betting advice.
          </p>
        </Section>
      </div>

      <div className="mt-8 flex justify-center">
        <Link
          href="/"
          className="rounded-full border border-gold/60 px-5 py-2 font-mono text-xs uppercase tracking-[0.18em] text-gold-text transition-colors hover:bg-gold hover:text-[#10241c]"
        >
          Back to the slate
        </Link>
      </div>
    </div>
  );
}
