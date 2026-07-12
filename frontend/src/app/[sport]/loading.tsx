import { WeekGridSkeleton } from "@/components/Skeletons";

export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="turf animate-pulse rounded-2xl px-6 py-10 sm:px-10 sm:py-14">
        <div className="h-3 w-48 rounded bg-chalk-soft/20" />
        <div className="mt-4 h-12 w-full max-w-xl rounded bg-chalk-soft/20" />
        <div className="mt-4 h-4 w-72 rounded bg-chalk-soft/20" />
      </div>
      <div className="mt-8 h-14 animate-pulse rounded-lg bg-surface" />
      <div className="mt-8">
        <WeekGridSkeleton />
      </div>
    </div>
  );
}
