// The Blitzcast football. Same drawing as scripts/icons/ball-32.svg; keep them in sync.
const TURF = "#1b4332";
const BAND = "#24563d";
const GOLD = "#e9b84d";

type Props = { size?: number; tile?: boolean; className?: string };

export default function BrandMark({ size = 24, tile = true, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      aria-hidden="true"
      data-brand-mark={tile ? "tile" : "ball"}
    >
      {tile && <rect width="64" height="64" rx="14" fill={TURF} />}
      {tile && <rect x="20" width="24" height="64" fill={BAND} />}
      <g transform="rotate(-30 32 32)">
        <ellipse cx="32" cy="32" rx="25" ry="16" fill={GOLD} />
        <path d="M20 32h24" stroke={TURF} strokeWidth="3.6" strokeLinecap="round" />
        <path d="M26 27.6v8.8M32 27v10M38 27.6v8.8" stroke={TURF} strokeWidth="3.4" strokeLinecap="round" />
      </g>
    </svg>
  );
}
