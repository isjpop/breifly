import { useParams } from 'react-router-dom'
import { ArticleCard } from '../components/ArticleCard'
import { SkeletonGrid } from '../components/CardSkeleton'
import { Pagination } from '../components/Pagination'
import { SortToggle } from '../components/SortToggle'
import { StatusMessage } from '../components/StatusMessage'
import { useAsync } from '../hooks/useAsync'
import { parsePage, useSearchParam } from '../hooks/usePageParam'
import { categoryFromParam, categoryLabel } from '../lib/categories'
import { api } from '../services/api'
import type { ArticleSort, CategorySlug } from '../types/api'
import { NotFoundPage } from './NotFoundPage'

const PER_PAGE = 18
const SORT_OPTIONS = [
  { value: 'importance', label: 'Most important' },
  { value: 'recent', label: 'Latest' },
] as const

export function CategoryPage() {
  const { slug } = useParams()
  const category = categoryFromParam(slug)
  if (!category) return <NotFoundPage />
  // Keyed so filters and paging reset cleanly when switching categories.
  return <CategoryFeed key={category} category={category} />
}

function CategoryFeed({ category }: { category: CategorySlug }) {
  const [sortParam, setSort] = useSearchParam('sort', 'importance')
  const [source, setSource] = useSearchParam('source')
  const [pageParam, setPage] = useSearchParam('page', '1')
  const sort: ArticleSort = sortParam === 'recent' ? 'recent' : 'importance'
  const page = parsePage(pageParam)

  const sources = useAsync((signal) => api.sources(signal), [])
  const feed = useAsync(
    (signal) => api.articles({ category, sort, source: source || undefined, page, perPage: PER_PAGE }, signal),
    [category, sort, source, page],
  )

  function changePage(next: number) {
    setPage(String(next))
    window.scrollTo({ top: 0 })
  }

  return (
    <div className="space-y-6">
      <header className="space-y-4 border-b border-line pb-5">
        <h1 className="font-serif text-3xl font-bold tracking-tight">{categoryLabel(category)}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <SortToggle label="Sort articles" value={sort} options={SORT_OPTIONS} onChange={(v) => setSort(v, ['page'])} />
          <label className="flex items-center gap-2 text-sm text-muted">
            <span>Publisher</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value, ['page'])}
              className="h-[34px] border border-line bg-surface px-2 text-sm text-ink focus:border-ink/40 focus:outline-none"
            >
              <option value="">All publishers</option>
              {sources.status === 'success' &&
                sources.data.map((s) => (
                  <option key={s.slug} value={s.slug}>
                    {s.name}
                  </option>
                ))}
            </select>
          </label>
          {feed.status === 'success' && (
            <p className="text-xs text-muted sm:ml-auto">{feed.data.pagination.total} articles</p>
          )}
        </div>
      </header>

      {feed.status === 'loading' && <SkeletonGrid label={`Loading ${categoryLabel(category)} stories`} />}

      {feed.status === 'error' && (
        <StatusMessage variant="error" title="Couldn’t load this feed" onRetry={feed.reload}>
          {feed.error.message}
        </StatusMessage>
      )}

      {feed.status === 'success' && feed.data.articles.length === 0 && (
        <StatusMessage variant="empty" title="No articles here yet">
          {source ? 'Try “All publishers” or another sort.' : 'New stories appear after each 15-minute update.'}
        </StatusMessage>
      )}

      {feed.status === 'success' && feed.data.articles.length > 0 && (
        <>
          <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {feed.data.articles.map((article) => (
              <ArticleCard key={article.id} article={article} showCategory={false} />
            ))}
          </div>
          <Pagination pagination={feed.data.pagination} onPageChange={changePage} />
        </>
      )}
    </div>
  )
}
