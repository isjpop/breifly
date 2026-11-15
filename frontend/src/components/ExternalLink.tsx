import { ArrowUpRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { safeExternalUrl } from '../lib/urls'

interface ExternalLinkProps {
  href: string | null | undefined
  children: ReactNode
  className?: string
  /** Shown instead of the link when the URL is missing or unsafe. */
  fallback?: ReactNode
}

/**
 * Link to a publisher's site. Always opens in a new tab, never passes the opener or referrer,
 * and carries a ↗ marker so it is visually distinct from in-app navigation.
 */
export function ExternalLink({ href, children, className = '', fallback = null }: ExternalLinkProps) {
  const url = safeExternalUrl(href)
  if (!url) return <>{fallback}</>
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-0.5 ${className}`}
    >
      {children}
      <ArrowUpRight size={14} aria-hidden className="shrink-0" />
      <span className="sr-only">(opens publisher site in a new tab)</span>
    </a>
  )
}
