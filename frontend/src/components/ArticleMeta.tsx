import { useNow } from '../hooks/useNow'
import { formatDateTime, formatRelative } from '../lib/format'
import type { SourceRef } from '../types/api'

interface ArticleMetaProps {
  source: SourceRef
  publishedAt: string | null
  firstSeenAt: string
  className?: string
}

/** "Publisher · 3 hr ago". Falls back to first-seen time when the feed gave no date. */
export function ArticleMeta({ source, publishedAt, firstSeenAt, className = '' }: ArticleMetaProps) {
  const now = useNow()
  const when = publishedAt ?? firstSeenAt
  return (
    <p className={`flex flex-wrap items-center gap-x-1.5 text-xs text-muted ${className}`}>
      <span className="font-medium text-ink/80">{source.name}</span>
      <span aria-hidden>·</span>
      <time dateTime={when} title={formatDateTime(when)}>
        {publishedAt ? formatRelative(when, now) : `seen ${formatRelative(when, now)}`}
      </time>
    </p>
  )
}
