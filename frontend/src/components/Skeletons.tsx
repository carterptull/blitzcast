export function GameCardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-edge bg-surface p-4">
      <div className="space-y-2.5">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="size-[34px] rounded-full bg-edge" />
            <div className="h-4 w-12 rounded bg-edge" />
            <div className="h-3 w-20 rounded bg-edge/70" />
            <div className="ml-auto h-3 w-8 rounded bg-edge/70" />
          </div>
        ))}
      </div>
      <div className="mt-3 h-1.5 rounded-full bg-edge" />
      <div className="mt-3 h-3 w-28 rounded bg-edge/70" />
    </div>
  );
}

export function WeekGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 9 }).map((_, i) => (
        <GameCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function MatchupSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="turf rounded-2xl px-5 py-12 sm:px-10">
        <div className="h-3 w-64 rounded bg-chalk-soft/20" />
        <div className="mt-8 grid gap-8 sm:grid-cols-[1fr_auto_1fr]">
          {[0, 1].map((i) => (
            <div
              key={i}
              className={`flex flex-col items-center gap-3 ${i === 0 ? "sm:items-start" : "sm:col-start-3 sm:items-end"}`}
            >
              <div className="size-[88px] rounded-full bg-chalk-soft/20" />
              <div className="h-7 w-32 rounded bg-chalk-soft/20" />
              <div className="h-14 w-28 rounded bg-chalk-soft/20" />
            </div>
          ))}
        </div>
        <div className="mt-8 h-4 rounded-md bg-chalk-soft/20 sm:h-5" />
      </div>
      <div className="h-32 rounded-xl border border-edge bg-surface" />
      <div className="h-64 rounded-xl border border-edge bg-surface" />
    </div>
  );
}
