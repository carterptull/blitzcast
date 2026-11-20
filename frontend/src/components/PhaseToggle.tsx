import Link from "next/link";
import type { SeasonType } from "@/lib/types";

interface Props {
  phase: SeasonType;
  regularHref: string;
  /** Null until a postseason slate exists, which hides the toggle. */
  postseasonHref: string | null;
}

/** Regular season / Postseason segmented pill. Each side opens that phase's
 *  default slate. */
export default function PhaseToggle({ phase, regularHref, postseasonHref }: Props) {
  if (postseasonHref === null) return null;

  const base =
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors";
  const off = "border-edge bg-surface text-ink-soft hover:border-gold/50 hover:text-ink";
  const on = "border-gold bg-stripe-a text-gold-turf";

  const sides = [
    { value: "regular", label: "Regular season", href: regularHref },
    { value: "postseason", label: "Postseason", href: postseasonHref },
  ] as const;

  return (
    <nav aria-label="Season phase" className="mt-6">
      <div className="inline-flex items-center gap-1 rounded-full border border-edge bg-surface p-1">
        {sides.map(({ value, label, href }) => {
          const active = value === phase;
          return (
            <Link
              key={value}
              href={href}
              scroll={false}
              prefetch={false}
              aria-current={active ? "true" : undefined}
              className={`${base} ${active ? on : off}`}
            >
              {label}
              {value === "postseason" && !active && (
                <span
                  data-testid="postseason-dot"
                  className="size-1.5 rounded-full bg-gold"
                  aria-hidden="true"
                />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
