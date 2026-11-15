interface ImportanceMeterProps {
  score: number | null
}

const SEGMENTS = 5

/** Five-segment meter plus the numeric score; high-importance stories use the accent color. */
export function ImportanceMeter({ score }: ImportanceMeterProps) {
  if (score === null) return null
  const filled = Math.max(1, Math.min(SEGMENTS, Math.round(score / 2)))
  const high = score >= 7.5
  return (
    <span
      className="inline-flex items-center gap-1.5"
      role="img"
      aria-label={`Importance ${score.toFixed(1)} out of 10`}
      title={`Importance ${score.toFixed(1)} / 10`}
    >
      <span className="flex gap-px" aria-hidden>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={`h-2.5 w-1 ${i < filled ? (high ? 'bg-accent' : 'bg-ink/60') : 'bg-line'}`}
          />
        ))}
      </span>
      <span className={`font-mono text-[11px] tabular-nums ${high ? 'text-accent' : 'text-muted'}`} aria-hidden>
        {score.toFixed(1)}
      </span>
    </span>
  )
}
