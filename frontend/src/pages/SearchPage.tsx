import { Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { ArticleCard } from '../components/ArticleCard'
import { SkeletonGrid } from '../components/CardSkeleton'
import { Pagination } from '../components/Pagination'
import { SortToggle } from '../components/SortToggle'
import { StatusMessage } from '../components/StatusMessage'
import { useAsync } from '../hooks/useAsync'
import { parsePage, useSearchParam } from '../hooks/usePageParam'
import { api } from '../services/api'
import type { PagedArticles, SearchSort } from '../types/api'

const PER_PAGE = 18
const MIN_QUERY = 2
const SORT_OPTIONS = [
  { value: 'relevance', label: 'Best match' },
  { value: 'recent', label: 'Latest' },
] as const

export function SearchPage() {
  const [query, setQuery] = useSearchParam('q')
  // Remount the form when the URL query changes (e.g. from the header search) so it shows it.
  return (
    <div className="space-y-6">
      <SearchForm key={query} initial={query} onSubmit={(q) => setQuery(q, ['page'])} />
      {query.trim().length >= MIN_QUERY ? (
        <SearchResults query={query.trim()} />
      ) : (
        <p className="text-sm text-muted">
          Search headlines, companies, people, topics and publishers. Use quotes for an exact phrase, and{' '}
          <code className="font-mono">-word</code> to exclude a term.
        </p>
      )}
    </div>
  )
}

function SearchForm({ initial, onSubmit }: { initial: string; onSubmit: (q: string) => void }) {
  const [value, setValue] = useState(initial)
  const tooShort = value.trim().length > 0 && value.trim().length < MIN_QUERY

  function submit(event: FormEvent) {
    event.preventDefault()
    if (value.trim().length >= MIN_QUERY) onSubmit(value.trim())
  }

  return (
    <form role="search" onSubmit={submit} className="space-y-2 border-b border-line pb-5">
      <h1 className="font-serif text-3xl font-bold tracking-tight">Search</h1>
      <div className="flex gap-2">
        <label htmlFor="search-input" className="sr-only">
          Search articles
        </label>
        <div className="relative flex-1">
          <Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            id="search-input"
            type="search"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={200}
            placeholder="e.g. Nvidia, interest rates, “fusion energy”"
            aria-describedby={tooShort ? 'search-hint' : undefined}
            className="h-10 w-full border border-line bg-surface pl-9 pr-3 text-base placeholder:text-muted focus:border-ink/40 focus:outline-none"
          />
        </div>
        <button type="submit" className="h-10 bg-ink px-4 text-sm font-medium text-canvas hover:opacity-90">
          Search
        </button>
      </div>
      {tooShort && (
        <p id="search-hint" className="text-xs text-muted">
          Enter at least {MIN_QUERY} characters.
        </p>
      )}
    </form>
  )
}

function SearchResults({ query }: { query: string }) {
  const [sortParam, setSort] = useSearchParam('sort', 'relevance')
  const [pageParam, setPage] = useSearchParam('page', '1')
  const sort: SearchSort = sortParam === 'recent' ? 'recent' : 'relevance'
  const page = parsePage(pageParam)
  const results = useAsync((signal) => api.search({ q: query, sort, page, perPage: PER_PAGE }, signal), [query, sort, page])

  return (
    <section aria-label="Search results" className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SortToggle label="Sort results" value={sort} options={SORT_OPTIONS} onChange={(v) => setSort(v, ['page'])} />
        {results.status === 'success' && <ResultCount data={results.data} query={query} />}
      </div>

      {results.status === 'loading' && <SkeletonGrid label="Searching" />}
      {results.status === 'error' && (
        <StatusMessage variant="error" title="Search failed" onRetry={results.reload}>
          {results.error.message}
        </StatusMessage>
      )}
      {results.status === 'success' && results.data.articles.length === 0 && (
        <StatusMessage variant="empty" title={`No articles match “${query}”`}>
          Try fewer or broader words, or a company or person’s name.
        </StatusMessage>
      )}
      {results.status === 'success' && results.data.articles.length > 0 && (
        <>
          <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {results.data.articles.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
          <Pagination
            pagination={results.data.pagination}
            onPageChange={(next) => {
              setPage(String(next))
              window.scrollTo({ top: 0 })
            }}
          />
        </>
      )}
    </section>
  )
}

function ResultCount({ data, query }: { data: PagedArticles; query: string }) {
  const total = data.pagination.total
  return (
    <p className="text-xs text-muted sm:ml-auto" aria-live="polite">
      {total} result{total === 1 ? '' : 's'} for <span className="font-medium text-ink">“{query}”</span>
    </p>
  )
}
