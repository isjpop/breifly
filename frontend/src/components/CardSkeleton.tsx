export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-3" aria-hidden>
      <div className="h-2.5 w-20 bg-line" />
      <div className="h-5 w-11/12 bg-line" />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3 bg-line/70" style={{ width: `${90 - i * 12}%` }} />
      ))}
      <div className="h-2.5 w-32 bg-line/70" />
    </div>
  )
}

/** Grid of skeleton cards announced once to assistive technology. */
export function SkeletonGrid({ count = 6, label = 'Loading stories' }: { count?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      <div className="grid gap-x-8 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }, (_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}
