import { Layers } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { categoryPath } from '../lib/categories'
import { safeExternalUrl } from '../lib/urls'
import type { ArticleCardData } from '../types/api'
import { ArticleMeta } from './ArticleMeta'
import { ExternalLink } from './ExternalLink'
import { ImportanceMeter } from './ImportanceMeter'
import { BasisTag, SummaryBlock } from './SummaryBlock'

export type CardVariant = 'lead' | 'standard' | 'compact'

interface ArticleCardProps {
  article: ArticleCardData
  variant?: CardVariant
  showCategory?: boolean
}

const TITLE_CLASSES: Record<CardVariant, string> = {
  lead: 'text-2xl sm:text-[1.7rem] leading-tight',
  standard: 'text-lg leading-snug',
  compact: 'text-base leading-snug',
}

export function ArticleCard({ article, variant = 'standard', showCategory = true }: ArticleCardProps) {
  const detailPath = `/article/${article.id}`
  const image = variant === 'lead' ? safeExternalUrl(article.image_url) : null

  return (
    <article className="flex h-full flex-col gap-2.5" aria-labelledby={`title-${article.id}`}>
      <div className="flex items-center justify-between gap-3">
        {showCategory && article.category ? (
          <Link
            to={categoryPath(article.category.slug)}
            className="text-[11px] font-semibold uppercase tracking-[0.08em] text-accent hover:underline"
          >
            {article.category.label}
          </Link>
        ) : (
          <span />
        )}
        <ImportanceMeter score={article.importance_score} />
      </div>

      {image && <LeadImage src={image} />}

      <h3 id={`title-${article.id}`} className={`font-serif font-semibold tracking-tight ${TITLE_CLASSES[variant]}`}>
        <Link to={detailPath} className="hover:text-accent">
          {article.title}
        </Link>
      </h3>

      <SummaryBlock
        summary={article.summary}
        description={article.description}
        maxBullets={variant === 'compact' ? 2 : 3}
        compact={variant === 'compact'}
      />

      {variant === 'lead' && article.summary?.status === 'succeeded' && article.summary.why_it_matters && (
        <p className="border-l-2 border-accent pl-3 text-sm leading-snug text-ink/85">
          <span className="font-semibold text-accent">Why it matters: </span>
          {article.summary.why_it_matters}
        </p>
      )}

      {/* Grid cards pin the footer to the bottom so footers align across a row; the lead card
          sits beside a taller column, so its footer follows the content directly. */}
      <div
        className={`${variant === 'lead' ? '' : 'mt-auto'} flex flex-wrap items-center justify-between gap-x-3 gap-y-1 pt-1`}
      >
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <ArticleMeta source={article.source} publishedAt={article.published_at} firstSeenAt={article.first_seen_at} />
          <BasisTag summary={article.summary} />
        </div>
        <div className="flex items-center gap-3 text-xs">
          {article.related_count > 0 && (
            <Link to={detailPath} className="inline-flex items-center gap-1 text-muted hover:text-ink">
              <Layers size={12} aria-hidden />+{article.related_count} source{article.related_count > 1 ? 's' : ''}
            </Link>
          )}
          <ExternalLink href={article.url} className="font-medium text-ink/80 hover:text-accent">
            Original
          </ExternalLink>
        </div>
      </div>
    </article>
  )
}

function LeadImage({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="aspect-[2/1] w-full border border-line object-cover"
    />
  )
}
