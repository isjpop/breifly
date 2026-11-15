import type { ArticleCardData, ArticleDetailData, Briefing, SourceInfo } from '../types/api'

let counter = 0

export function makeArticle(overrides: Partial<ArticleCardData> = {}): ArticleCardData {
  counter += 1
  return {
    id: `00000000-0000-0000-0000-${String(counter).padStart(12, '0')}`,
    title: `Story number ${counter}`,
    url: `https://publisher.example.com/story-${counter}`,
    source: { slug: 'wire', name: 'Global Wire' },
    author: 'Jane Reporter',
    published_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
    first_seen_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
    category: { slug: 'finance', label: 'Finance' },
    importance_score: 6.5,
    image_url: null,
    description: 'Publisher description of the story.',
    summary: {
      status: 'succeeded',
      headline: 'AI headline',
      bullet_points: ['First takeaway.', 'Second takeaway.', 'Third takeaway.', 'Fourth takeaway.'],
      why_it_matters: 'It matters because of reasons.',
      source_coverage: 'article_text',
      limitations: null,
    },
    related_count: 0,
    ...overrides,
  }
}

export function makeDetail(overrides: Partial<ArticleDetailData> = {}): ArticleDetailData {
  const card = makeArticle()
  return {
    ...card,
    content_availability: 'feed_content',
    tags: [],
    summary: {
      status: 'succeeded',
      headline: 'AI headline',
      bullet_points: ['First takeaway.', 'Second takeaway.', 'Third takeaway.', 'Fourth takeaway.'],
      why_it_matters: 'It matters because of reasons.',
      source_coverage: 'article_text',
      limitations: null,
      key_entities: ['Acme Corp', 'Jane Doe'],
      model_name: 'gemini-3.5-flash-lite',
      generated_at: new Date().toISOString(),
    },
    related: [],
    ...overrides,
  }
}

export function makeBriefing(overrides: Partial<Briefing> = {}): Briefing {
  return {
    generated_at: new Date().toISOString(),
    last_updated_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    window_start: new Date(Date.now() - 24 * 3_600_000).toISOString(),
    window_hours: 24,
    top_stories: [makeArticle({ title: 'Lead story' }), makeArticle({ title: 'Second story' })],
    sections: [
      {
        category: { slug: 'technology', label: 'Technology' },
        articles: [makeArticle({ title: 'Tech story', category: { slug: 'technology', label: 'Technology' } })],
      },
    ],
    ...overrides,
  }
}

export const SOURCES: SourceInfo[] = [
  {
    slug: 'wire',
    name: 'Global Wire',
    homepage_url: 'https://wire.example.com',
    default_category: { slug: 'finance', label: 'Finance' },
    credibility_weight: 0.9,
    is_active: true,
    last_successful_fetch_at: null,
    last_fetch_status: 'success',
  },
  {
    slug: 'techdesk',
    name: 'Tech Desk',
    homepage_url: 'https://techdesk.example.com',
    default_category: { slug: 'technology', label: 'Technology' },
    credibility_weight: 0.8,
    is_active: true,
    last_successful_fetch_at: null,
    last_fetch_status: 'success',
  },
]

export function paged(articles: ArticleCardData[], page = 1, totalPages = 1) {
  return {
    data: articles,
    meta: { pagination: { page, per_page: 18, total: articles.length * totalPages, total_pages: totalPages } },
  }
}
