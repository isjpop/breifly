import type {
  ApiErrorBody,
  ApiSuccess,
  ArticleCardData,
  ArticleDetailData,
  ArticleSort,
  Briefing,
  CategoryInfo,
  CategorySlug,
  HealthStatus,
  PagedArticles,
  Pagination,
  SearchSort,
  SourceInfo,
} from '../types/api'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const DEFAULT_TIMEOUT_MS = 10_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorBody).error?.message === 'string'
  )
}

/**
 * Fetch a JSON endpoint and unwrap the `{data, meta}` envelope.
 * Network failures, timeouts and non-2xx responses all surface as `ApiError`.
 * When `allowErrorStatus` is set, a non-2xx response that still carries a data envelope
 * (e.g. /api/health returning 503 "degraded") is returned instead of thrown.
 */
export async function getJson<T>(
  path: string,
  { signal, allowErrorStatus = false }: { signal?: AbortSignal; allowErrorStatus?: boolean } = {},
): Promise<ApiSuccess<T>> {
  const timeout = AbortSignal.timeout(DEFAULT_TIMEOUT_MS)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
      signal: combined,
    })
  } catch (err) {
    if (signal?.aborted) throw err
    if (timeout.aborted) throw new ApiError(0, 'timeout', 'The server took too long to respond.')
    throw new ApiError(0, 'network_error', 'Unable to reach the Briefly server.')
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON body (e.g. a proxy error page); handled below.
  }

  if (response.ok || (allowErrorStatus && body && typeof body === 'object' && 'data' in body)) {
    if (body && typeof body === 'object' && 'data' in body) return body as ApiSuccess<T>
    throw new ApiError(response.status, 'invalid_response', 'The server returned an unexpected response.')
  }

  if (isErrorBody(body)) throw new ApiError(response.status, body.error.code, body.error.message)
  throw new ApiError(response.status, 'http_error', `Request failed with status ${response.status}.`)
}

type QueryValue = string | number | undefined | null

/** Build a query string, dropping empty values. */
export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function paged(response: ApiSuccess<ArticleCardData[]>): PagedArticles {
  const pagination = response.meta?.pagination as Pagination | undefined
  return {
    articles: response.data,
    pagination: pagination ?? { page: 1, per_page: response.data.length, total: response.data.length, total_pages: 1 },
  }
}

export interface ArticleQuery {
  category?: CategorySlug
  source?: string
  sort?: ArticleSort
  page?: number
  perPage?: number
}

export interface SearchQuery {
  q: string
  sort?: SearchSort
  page?: number
  perPage?: number
}

export const api = {
  health: (signal?: AbortSignal) =>
    getJson<HealthStatus>('/api/health', { signal, allowErrorStatus: true }),

  briefing: async (signal?: AbortSignal) =>
    (await getJson<Briefing>('/api/briefing/today', { signal })).data,

  articles: async (query: ArticleQuery, signal?: AbortSignal) =>
    paged(
      await getJson<ArticleCardData[]>(
        `/api/articles${buildQuery({
          category: query.category,
          source: query.source,
          sort: query.sort,
          page: query.page,
          per_page: query.perPage,
        })}`,
        { signal },
      ),
    ),

  search: async (query: SearchQuery, signal?: AbortSignal) =>
    paged(
      await getJson<ArticleCardData[]>(
        `/api/articles/search${buildQuery({
          q: query.q,
          sort: query.sort,
          page: query.page,
          per_page: query.perPage,
        })}`,
        { signal },
      ),
    ),

  article: async (id: string, signal?: AbortSignal) =>
    (await getJson<ArticleDetailData>(`/api/articles/${encodeURIComponent(id)}`, { signal })).data,

  categories: async (signal?: AbortSignal) =>
    (await getJson<CategoryInfo[]>('/api/categories', { signal })).data,

  sources: async (signal?: AbortSignal) =>
    (await getJson<SourceInfo[]>('/api/sources', { signal })).data,
}
