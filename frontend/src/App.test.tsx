import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppRoutes } from './App'
import { SOURCES, makeArticle, makeBriefing, paged } from './test/fixtures'
import { mockApi } from './test/mockApi'

describe('AppRoutes', () => {
  it('navigates from the briefing to a category feed and resets scroll', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    mockApi({
      '/api/briefing/today': { body: { data: makeBriefing() } },
      '/api/sources': { body: { data: SOURCES } },
      '/api/articles': { body: paged([makeArticle({ title: 'Science story' })]) },
    })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Daily Briefing' })).toBeInTheDocument()
    scrollTo.mockClear()
    await userEvent.click(screen.getByRole('link', { name: 'Science' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Science' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Science story' })).toBeInTheDocument()
    expect(scrollTo).toHaveBeenCalledWith({ top: 0 })
  })

  it('renders not found for unknown routes', () => {
    mockApi({})
    render(
      <MemoryRouter initialEntries={['/nope']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByText('We couldn’t find that page')).toBeInTheDocument()
  })
})
