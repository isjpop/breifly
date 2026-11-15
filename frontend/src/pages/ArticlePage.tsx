import { ArrowLeft, Layers, Sparkles } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExternalLink } from '../components/ExternalLink'
import { ImportanceMeter } from '../components/ImportanceMeter'
import { CoverageNote } from '../components/SummaryBlock'
import { StatusMessage } from '../components/StatusMessage'
import { useAsync } from '../hooks/useAsync'
import { useNow } from '../hooks/useNow'
import { categoryPath } from '../lib/categories'
import { formatDateTime, formatRelative } from '../lib/format'
import { ApiError, api } from '../services/api'
import type { ArticleDetailData, SummaryDetail } from '../types/api'
import { NotFoundPage } from './NotFoundPage'

export function ArticlePage() {
  const { id = '' } = useParams()
  const article = useAsync((signal) => api.article(id, signal), [id])

  if (article.status === 'loading') return <ArticleSkeleton />
  if (article.status === 'error') {
    const error = article.error
    if (error instanceof ApiError && (error.status === 404 || error.code === 'invalid_id')) return <NotFoundPage />
    return (
      <StatusMessage variant="error" title="Couldn’t load this article" onRetry={article.reload}>
        {error.message}
      </StatusMessage>
    )
  }
  return <ArticleView article={article.data} />
}

function ArticleView({ article }: { article: ArticleDetailData }) {
  const navigate = useNavigate()
  const now = useNow()
  const when = article.published_at ?? article.first_seen_at

  return (
    <article className="mx-auto max-w-3xl space-y-8">
      <button
        type="button"
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"
      >
        <ArrowLeft size={14} aria-hidden /> Back
      </button>

      <header className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          {article.category ? (
            <Link
              to={categoryPath(article.category.slug)}
              className="text-xs font-semibold uppercase tracking-[0.08em] text-accent hover:underline"
            >
              {article.category.label}
            </Link>
          ) : (
            <span />
          )}
          <ImportanceMeter score={article.importance_score} />
        </div>
        <h1 className="font-serif text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{article.title}</h1>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
          <span className="font-semibold text-ink">{article.source.name}</span>
          {article.author && (
            <>
              <span aria-hidden>·</span>
              <span>{article.author}</span>
            </>
          )}
          <span aria-hidden>·</span>
          <time dateTime={when} title={formatRelative(when, now)}>
            {formatDateTime(when)}
          </time>
        </div>
        <ExternalLink
          href={article.url}
          className="border border-ink px-3 py-2 text-sm font-medium transition-colors hover:bg-ink hover:text-canvas"
          fallback={<p className="text-sm text-muted">The original link is unavailable.</p>}
        >
          Read the full story at {article.source.name}
        </ExternalLink>
      </header>

      <SummarySection summary={article.summary} description={article.description} />

      {article.summary?.key_entities && article.summary.key_entities.length > 0 && (
        <section aria-labelledby="entities" className="space-y-2">
          <h2 id="entities" className="text-xs font-bold uppercase tracking-[0.12em]">
            Mentioned
          </h2>
          <ul className="flex flex-wrap gap-2">
            {article.summary.key_entities.map((entity) => (
              <li key={entity}>
                <Link
                  to={`/search?q=${encodeURIComponent(`"${entity}"`)}`}
                  className="inline-block border border-line px-2 py-1 text-xs hover:border-ink/40"
                  title={`Search for ${entity}`}
                >
                  {entity}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {article.related.length > 0 && (
        <section aria-labelledby="related" className="space-y-3">
          <h2 id="related" className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.12em]">
            <Layers size={13} aria-hidden /> Also covered by
          </h2>
          <ul className="divide-y divide-line border-y border-line">
            {article.related.map((related) => (
              <li key={related.id} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                <div>
                  <p className="text-xs font-semibold text-muted">{related.source.name}</p>
                  <Link to={`/article/${related.id}`} className="font-serif text-base hover:text-accent">
                    {related.title}
                  </Link>
                </div>
                <ExternalLink href={related.url} className="shrink-0 text-xs text-muted hover:text-ink">
                  Original
                </ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}

function SummarySection({ summary, description }: { summary: SummaryDetail | null; description: string | null }) {
  if (!summary || summary.status !== 'succeeded') {
    const note =
      summary?.status === 'insufficient_content'
        ? 'The publisher’s feed provides too little text for an AI summary. Read the original for the full story.'
        : 'An AI summary hasn’t been generated for this article yet.'
    return (
      <section aria-labelledby="summary" className="space-y-3 border-l-2 border-line pl-4">
        <h2 id="summary" className="text-xs font-bold uppercase tracking-[0.12em]">
          From the publisher
        </h2>
        {description && <p className="text-base leading-relaxed">{description}</p>}
        <CoverageNote>{summary?.limitations ?? note}</CoverageNote>
      </section>
    )
  }

  return (
    <section aria-labelledby="summary" className="space-y-5">
      <div className="space-y-3">
        <h2 id="summary" className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.12em]">
          <Sparkles size={13} aria-hidden className="text-accent" /> Key takeaways
        </h2>
        <ul className="space-y-2.5 text-base leading-relaxed">
          {summary.bullet_points.map((point) => (
            <li
              key={point}
              className="relative pl-5 before:absolute before:left-0 before:top-[0.6em] before:h-1.5 before:w-1.5 before:bg-accent"
            >
              {point}
            </li>
          ))}
        </ul>
      </div>

      {summary.why_it_matters && (
        <div className="border-l-2 border-accent bg-surface px-4 py-3">
          <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-accent">Why it matters</h3>
          <p className="mt-1 text-base leading-relaxed">{summary.why_it_matters}</p>
        </div>
      )}

      <div className="space-y-1">
        {summary.source_coverage === 'excerpt' && (
          <CoverageNote>Based only on the publisher’s excerpt, not the full article.</CoverageNote>
        )}
        {summary.limitations && summary.source_coverage !== 'excerpt' && <CoverageNote>{summary.limitations}</CoverageNote>}
        <p className="text-[11px] text-muted">
          AI-generated summary{summary.model_name && <> · {summary.model_name}</>}
          {summary.generated_at && <> · {formatDateTime(summary.generated_at)}</>}. May contain errors — check the
          original.
        </p>
      </div>
    </section>
  )
}

function ArticleSkeleton() {
  return (
    <div role="status" aria-live="polite" className="mx-auto max-w-3xl animate-pulse space-y-5">
      <span className="sr-only">Loading article…</span>
      <div className="h-3 w-24 bg-line" />
      <div className="h-9 w-full bg-line" />
      <div className="h-9 w-2/3 bg-line" />
      <div className="h-3 w-48 bg-line/70" />
      <div className="space-y-3 pt-4">
        {[92, 85, 88, 70].map((w) => (
          <div key={w} className="h-4 bg-line/70" style={{ width: `${w}%` }} />
        ))}
      </div>
    </div>
  )
}
