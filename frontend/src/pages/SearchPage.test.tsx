import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { makeArticle, paged } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { SearchPage } from './SearchPage'

const route = [{ path: '/search', element: <SearchPage /> }]

describe('SearchPage', () => {
  it('shows guidance and makes no request without a query', () => {
    const mock = mockApi({})
    renderAt('/search', route)
    expect(screen.getByText(/Search headlines, companies, people/)).toBeInTheDocument()
    expect(mock.calls).toHaveLength(0)
  })

  it('submits a query to the URL and the API', async () => {
    const mock = mockApi({ '/api/articles/search': { body: paged([makeArticle({ title: 'Nvidia result' })]) } })
    renderAt('/search', route)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search articles' }), 'nvidia chips')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByRole('heading', { name: 'Nvidia result' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/search?q=nvidia+chips')
    expect(mock.lastCall('/api/articles/search')!.searchParams.get('q')).toBe('nvidia chips')
    expect(screen.getByText(/1 result for/)).toBeInTheDocument()
  })

  it('does not search for single characters', async () => {
    const mock = mockApi({})
    renderAt('/search', route)
    await userEvent.type(screen.getByRole('searchbox'), 'a')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(screen.getByText('Enter at least 2 characters.')).toBeInTheDocument()
    expect(mock.calls).toHaveLength(0)
  })

  it('loads results from the URL and shows an empty state', async () => {
    mockApi({ '/api/articles/search': { body: paged([]) } })
    renderAt('/search?q=zzzz', route)
    expect(screen.getByRole('searchbox')).toHaveValue('zzzz')
    expect(await screen.findByText('No articles match “zzzz”')).toBeInTheDocument()
  })

  it('changes sort order', async () => {
    const mock = mockApi({ '/api/articles/search': { body: paged([makeArticle()]) } })
    renderAt('/search?q=fed', route)
    await userEvent.click(await screen.findByRole('radio', { name: 'Latest' }))
    await screen.findByText(/1 result for/)
    expect(mock.lastCall('/api/articles/search')!.searchParams.get('sort')).toBe('recent')
  })

  it('shows API errors', async () => {
    mockApi({ '/api/articles/search': { status: 503, body: { error: { code: 'database_unavailable', message: 'Down.' } } } })
    renderAt('/search?q=fed', route)
    expect(await screen.findByRole('alert')).toHaveTextContent('Search failed')
  })
})
