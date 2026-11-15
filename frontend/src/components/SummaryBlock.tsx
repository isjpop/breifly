import { Info } from 'lucide-react'
import { summaryBasis } from '../lib/summary'
import type { SummaryPreview } from '../types/api'

interface SummaryBlockProps {
  summary: SummaryPreview | null
  description: string | null
  maxBullets?: number
  compact?: boolean
}

/**
 * The card body. Shows AI takeaways when available and is explicit about their basis:
 * excerpt-only summaries are labelled, and articles without a summary fall back to the
 * publisher's own description rather than showing nothing.
 */
export function SummaryBlock({ summary, description, maxBullets = 3, compact = false }: SummaryBlockProps) {
  const textSize = compact ? 'text-[13px]' : 'text-sm'
  if (summary?.status === 'succeeded' && summary.bullet_points.length > 0) {
    return (
      <div className="space-y-1.5">
        <ul className={`space-y-1 ${textSize} leading-snug text-ink/90`}>
          {summary.bullet_points.slice(0, maxBullets).map((point) => (
            <li key={point} className="relative pl-3.5 before:absolute before:left-0 before:top-[0.55em] before:h-1 before:w-1 before:bg-accent">
              {point}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return description ? <p className={`${textSize} leading-snug text-ink/80`}>{description}</p> : null
}

export function BasisTag({ summary }: { summary: SummaryPreview | null }) {
  const basis = summaryBasis(summary)
  if (!basis) return null
  return (
    <span title={basis.title} className="inline-flex items-center gap-1 text-[11px] text-muted">
      <Info size={11} aria-hidden />
      <span>{basis.label}</span>
      <span className="sr-only">: {basis.title}</span>
    </span>
  )
}

export function CoverageNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-1 text-[11px] text-muted">
      <Info size={12} aria-hidden className="shrink-0" />
      {children}
    </p>
  )
}
