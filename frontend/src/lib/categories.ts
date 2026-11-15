import type { CategorySlug } from '../types/api'

/** Display order and labels; mirrors the backend's category list. */
export const CATEGORIES: ReadonlyArray<{ slug: CategorySlug; label: string }> = [
  { slug: 'finance', label: 'Finance' },
  { slug: 'technology', label: 'Technology' },
  { slug: 'business', label: 'Business' },
  { slug: 'science', label: 'Science' },
  { slug: 'breaking_news', label: 'Breaking News' },
]

/** URL segments use hyphens (/category/breaking-news); the API uses underscores. */
export function categoryPath(slug: CategorySlug): string {
  return `/category/${slug.replace('_', '-')}`
}

export function categoryFromParam(param: string | undefined): CategorySlug | null {
  const slug = (param ?? '').replace('-', '_')
  return CATEGORIES.some((c) => c.slug === slug) ? (slug as CategorySlug) : null
}

export function categoryLabel(slug: CategorySlug): string {
  return CATEGORIES.find((c) => c.slug === slug)?.label ?? slug
}
