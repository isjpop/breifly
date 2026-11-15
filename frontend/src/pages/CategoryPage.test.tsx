import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SOURCES, makeArticle, paged } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { CategoryPage } from './CategoryPage'

const route = [{ path: '/category/:slug', element: <CategoryPage /> }]

function api(articles = [makeArticle({ title: 'Finance story' })], totalPages = 1) {
  return mockApi({
    '/api/sources': { body: { data: SOURCES } },
    '/api/articles': (url) => ({ body: paged(articles, Number(url.searchParams.get('page') ?? 1), totalPages) }),
  })
}

describe('CategoryPage', () => {
  it('requests the category feed sorted by importance by default', async () => {
    const mock = api()
    renderAt('/category/finance', route)

    expect(await screen.findByRole('heading', { name: 'Finance story' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Finance' })).toBeInTheDocument()
    const call = mock.lastCall('/api/articles')!
    expect(call.searchParams.get('category')).toBe('finance')
    expect(call.searchParams.get('sort')).toBe('importance')
  })

  it('maps hyphenated URLs to API categories', async () => {
    const mock = api()
    renderAt('/category/breaking-news', route)
    await screen.findByRole('heading', { name: 'Finance story' })
    expect(mock.lastCall('/api/articles')!.searchParams.get('category')).toBe('breaking_news')
  })

  it('filters by sort and publisher via the URL', async () => {
    const mock = api()
    renderAt('/category/finance', route)
    await screen.findByRole('heading', { name: 'Finance story' })

    await userEvent.click(screen.getByRole('radio', { name: 'Latest' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/category/finance?sort=recent')
    await screen.findByRole('heading', { name: 'Finance story' })
    expect(mock.lastCall('/api/articles')!.searchParams.get('sort')).toBe('recent')

    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Publisher' }), 'techdesk')
    await screen.findByRole('heading', { name: 'Finance story' })
    expect(mock.lastCall('/api/articles')!.searchParams.get('source')).toBe('techdesk')
  })

  it('paginates', async () => {
    const mock = api([makeArticle()], 3)
    renderAt('/category/finance', route)
    await userEvent.click(await screen.findByRole('button', { name: /Next/ }))
    expect(screen.getByTestId('location')).toHaveTextContent('page=2')
    await screen.findByText(/Page/)
    expect(mock.lastCall('/api/articles')!.searchParams.get('page')).toBe('2')
    expect(screen.getByRole('button', { name: /Previous/ })).toBeEnabled()
  })

  it('shows an empty state', async () => {
    api([])
    renderAt('/category/science', route)
    expect(await screen.findByText('No articles here yet')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    mockApi({
      '/api/sources': { body: { data: SOURCES } },
      '/api/articles': { status: 500, body: { error: { code: 'internal_error', message: 'An unexpected error occurred.' } } },
    })
    renderAt('/category/finance', route)
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load this feed')
  })

  it('treats unknown categories as not found without calling the API', () => {
    const mock = api()
    renderAt('/category/sports', route)
    expect(screen.getByText('We couldn’t find that page')).toBeInTheDocument()
    expect(mock.calls).toHaveLength(0)
  })
})
