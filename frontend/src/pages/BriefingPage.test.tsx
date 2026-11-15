import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { makeBriefing } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { BriefingPage } from './BriefingPage'

const renderBriefing = () => renderAt('/', [{ path: '/', element: <BriefingPage /> }])

describe('BriefingPage', () => {
  it('shows a loading state while the briefing loads', () => {
    mockApi({ '/api/briefing/today': 'pending' })
    renderBriefing()
    expect(screen.getByRole('status')).toHaveTextContent('Loading today’s briefing')
  })

  it('renders top stories, the update time and category sections', async () => {
    mockApi({ '/api/briefing/today': { body: { data: makeBriefing() } } })
    renderBriefing()

    const top = await screen.findByRole('region', { name: 'Top stories' })
    expect(within(top).getByRole('heading', { name: 'Lead story' })).toBeInTheDocument()
    expect(within(top).getByRole('heading', { name: 'Second story' })).toBeInTheDocument()

    const tech = screen.getByRole('region', { name: 'Technology' })
    expect(within(tech).getByRole('heading', { name: 'Tech story' })).toBeInTheDocument()
    expect(within(tech).getByRole('link', { name: /All Technology/ })).toHaveAttribute('href', '/category/technology')
    expect(screen.getByText(/Updated/)).toHaveTextContent('5 min. ago')
  })

  it('mentions a widened window', async () => {
    mockApi({ '/api/briefing/today': { body: { data: makeBriefing({ window_hours: 72 }) } } })
    renderBriefing()
    expect(await screen.findByText(/covering the last 3 days/)).toBeInTheDocument()
  })

  it('shows an empty state when there are no stories', async () => {
    mockApi({
      '/api/briefing/today': { body: { data: makeBriefing({ top_stories: [], sections: [], last_updated_at: null }) } },
    })
    renderBriefing()
    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
    expect(screen.getByText('Awaiting first news update')).toBeInTheDocument()
  })

  it('shows API errors and recovers on retry', async () => {
    let fail = true
    mockApi({
      '/api/briefing/today': () =>
        fail
          ? { status: 503, body: { error: { code: 'database_unavailable', message: 'The database is temporarily unavailable.' } } }
          : { body: { data: makeBriefing() } },
    })
    renderBriefing()

    expect(await screen.findByRole('alert')).toHaveTextContent('The database is temporarily unavailable.')
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Lead story' })).toBeInTheDocument()
  })

  it('reports network failures in plain language', async () => {
    mockApi({ '/api/briefing/today': new TypeError('Failed to fetch') })
    renderBriefing()
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the Briefly server.')
  })
})
