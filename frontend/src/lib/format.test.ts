import { describe, expect, it } from 'vitest'
import { categoryFromParam, categoryPath } from './categories'
import { formatRelative } from './format'
import { safeExternalUrl } from './urls'

const NOW = new Date('2026-11-15T12:00:00Z')

describe('formatRelative', () => {
  it.each([
    ['2026-11-15T11:59:40Z', 'just now'],
    ['2026-11-15T11:48:00Z', '12 min. ago'],
    ['2026-11-15T09:00:00Z', '3 hr. ago'],
    ['2026-11-14T10:00:00Z', 'yesterday'],
  ])('%s → %s', (iso, expected) => {
    expect(formatRelative(iso, NOW)).toBe(expected)
  })

  it('falls back to a date beyond a week and tolerates bad input', () => {
    expect(formatRelative('2026-10-01T00:00:00Z', NOW)).toMatch(/2026/)
    expect(formatRelative('not a date', NOW)).toBe('')
  })
})

describe('categories', () => {
  it('round-trips URL segments', () => {
    expect(categoryPath('breaking_news')).toBe('/category/breaking-news')
    expect(categoryFromParam('breaking-news')).toBe('breaking_news')
    expect(categoryFromParam('sports')).toBeNull()
    expect(categoryFromParam(undefined)).toBeNull()
  })
})

describe('safeExternalUrl', () => {
  it('allows only absolute http(s) URLs', () => {
    expect(safeExternalUrl('https://example.com/a')).toBe('https://example.com/a')
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(safeExternalUrl('/relative')).toBeNull()
    expect(safeExternalUrl('data:text/html,x')).toBeNull()
    expect(safeExternalUrl(null)).toBeNull()
  })
})
