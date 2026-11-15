import { ArticleCard } from '../components/ArticleCard'
import { CardSkeleton, SkeletonGrid } from '../components/CardSkeleton'
import { SectionHeading } from '../components/SectionHeading'
import { StatusMessage } from '../components/StatusMessage'
import { useAsync } from '../hooks/useAsync'
import { useNow } from '../hooks/useNow'
import { categoryPath } from '../lib/categories'
import { formatDateTime, formatLongDate, formatRelative } from '../lib/format'
import { api } from '../services/api'
import type { Briefing } from '../types/api'

export function BriefingPage() {
  const briefing = useAsync((signal) => api.briefing(signal), [])
  const now = useNow()

  return (
    <div className="space-y-10">
      <header className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.12em] text-muted">{formatLongDate(now)}</p>
          <h1 className="font-serif text-3xl font-bold tracking-tight">Daily Briefing</h1>
        </div>
        {briefing.status === 'success' && <UpdatedLine briefing={briefing.data} now={now} />}
      </header>

      {briefing.status === 'loading' && <BriefingSkeleton />}

      {briefing.status === 'error' && (
        <StatusMessage variant="error" title="Couldn’t load today’s briefing" onRetry={briefing.reload}>
          {briefing.error.message}
        </StatusMessage>
      )}

      {briefing.status === 'success' && <BriefingContent briefing={briefing.data} />}
    </div>
  )
}

function UpdatedLine({ briefing, now }: { briefing: Briefing; now: Date }) {
  return (
    <p className="text-xs text-muted">
      {briefing.last_updated_at ? (
        <>
          Updated{' '}
          <time dateTime={briefing.last_updated_at} title={formatDateTime(briefing.last_updated_at)}>
            {formatRelative(briefing.last_updated_at, now)}
          </time>
        </>
      ) : (
        'Awaiting first news update'
      )}
      {briefing.window_hours > 24 && <> · covering the last {Math.round(briefing.window_hours / 24)} days</>}
    </p>
  )
}

function BriefingContent({ briefing }: { briefing: Briefing }) {
  const [lead, ...others] = briefing.top_stories
  if (!lead) {
    return (
      <StatusMessage variant="empty" title="No stories yet">
        Briefly checks its sources every 15 minutes. New stories will appear here after the next update.
      </StatusMessage>
    )
  }

  return (
    <>
      <section aria-labelledby="top-stories">
        <SectionHeading id="top-stories">Top stories</SectionHeading>
        <div className="grid gap-8 lg:grid-cols-3">
          <div className="lg:col-span-2 lg:border-r lg:border-line lg:pr-8">
            <ArticleCard article={lead} variant="lead" />
          </div>
          {others.length > 0 && (
            <ol className="divide-y divide-line">
              {others.map((article) => (
                <li key={article.id} className="py-4 first:pt-0 last:pb-0">
                  <ArticleCard article={article} variant="compact" />
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      {briefing.sections.map((section) => {
        const headingId = `section-${section.category.slug}`
        return (
          <section key={section.category.slug} aria-labelledby={headingId}>
            <SectionHeading id={headingId} moreTo={categoryPath(section.category.slug)} moreLabel={`All ${section.category.label}`}>
              {section.category.label}
            </SectionHeading>
            <div className="grid gap-x-8 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
              {section.articles.map((article) => (
                <ArticleCard key={article.id} article={article} showCategory={false} />
              ))}
            </div>
          </section>
        )
      })}
    </>
  )
}

function BriefingSkeleton() {
  return (
    <div className="space-y-10">
      <div role="status" aria-live="polite">
        <span className="sr-only">Loading today’s briefing…</span>
        <div className="grid gap-8 lg:grid-cols-3" aria-hidden>
          <div className="space-y-3 lg:col-span-2">
            <div className="aspect-[2/1] w-full animate-pulse bg-line/70" />
            <CardSkeleton lines={3} />
          </div>
          <div className="space-y-6">
            <CardSkeleton lines={2} />
            <CardSkeleton lines={2} />
          </div>
        </div>
      </div>
      <div aria-hidden>
        <SkeletonGrid count={3} label="Loading sections" />
      </div>
    </div>
  )
}
