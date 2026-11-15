import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface SectionHeadingProps {
  id: string
  children: ReactNode
  moreTo?: string
  moreLabel?: string
}

/** Rule-topped section label in the style of a newspaper section break. */
export function SectionHeading({ id, children, moreTo, moreLabel = 'View all' }: SectionHeadingProps) {
  return (
    <div className="mb-5 flex items-baseline justify-between border-t-2 border-ink pt-2">
      <h2 id={id} className="text-xs font-bold uppercase tracking-[0.12em]">
        {children}
      </h2>
      {moreTo && (
        <Link to={moreTo} className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
          {moreLabel} <ArrowRight size={12} aria-hidden />
        </Link>
      )}
    </div>
  )
}
