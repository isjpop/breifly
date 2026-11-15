/**
 * Types mirroring the Flask API (backend/app/schemas/api.py and docs/api.md).
 * Keep in sync with the backend's response models.
 */

export interface ApiSuccess<T> {
  data: T
  meta?: Record<string, unknown>
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, string>
  }
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
  timestamp: string
}

export type CategorySlug = 'finance' | 'technology' | 'business' | 'science' | 'breaking_news'

export interface CategoryRef {
  slug: CategorySlug
  label: string
}

export interface SourceRef {
  slug: string
  name: string
}

export type SummaryStatus = 'succeeded' | 'insufficient_content' | 'failed'
export type SourceCoverage = 'article_text' | 'excerpt'

export interface SummaryPreview {
  status: SummaryStatus
  headline: string | null
  bullet_points: string[]
  why_it_matters: string | null
  source_coverage: SourceCoverage | null
  limitations: string | null
}

export interface SummaryDetail extends SummaryPreview {
  key_entities: string[]
  model_name: string | null
  generated_at: string | null
}

export interface ArticleCardData {
  id: string
  title: string
  url: string | null
  source: SourceRef
  author: string | null
  published_at: string | null
  first_seen_at: string
  category: CategoryRef | null
  importance_score: number | null
  image_url: string | null
  description: string | null
  summary: SummaryPreview | null
  related_count: number
}

export interface RelatedArticle {
  id: string
  title: string
  url: string | null
  source: SourceRef
  published_at: string | null
}

export interface ArticleDetailData extends Omit<ArticleCardData, 'summary'> {
  content_availability: 'feed_content' | 'description_only' | 'headline_only'
  tags: string[]
  summary: SummaryDetail | null
  related: RelatedArticle[]
}

export interface Pagination {
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface PagedArticles {
  articles: ArticleCardData[]
  pagination: Pagination
}

export interface CategoryInfo extends CategoryRef {
  article_count: number
}

export interface SourceInfo extends SourceRef {
  homepage_url: string | null
  default_category: CategoryRef
  credibility_weight: number
  is_active: boolean
  last_successful_fetch_at: string | null
  last_fetch_status: 'success' | 'not_modified' | 'failed' | null
}

export interface BriefingSection {
  category: CategoryRef
  articles: ArticleCardData[]
}

export interface Briefing {
  generated_at: string
  last_updated_at: string | null
  window_start: string
  window_hours: number
  top_stories: ArticleCardData[]
  sections: BriefingSection[]
}

export type ArticleSort = 'importance' | 'recent'
export type SearchSort = 'relevance' | 'recent'
