import { MatchupSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="mb-4 h-3 w-32 animate-pulse rounded bg-edge" />
      <MatchupSkeleton />
    </div>
  );
}
