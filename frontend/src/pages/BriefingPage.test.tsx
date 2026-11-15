import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { BriefingPage } from './BriefingPage'

const okBody = { data: { status: 'ok', database: 'ok', timestamp: '2026-11-14T00:00:00Z' } }

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('BriefingPage', () => {
  it('shows a loading state while the request is pending', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    render(<BriefingPage />)
    expect(screen.getByText('Connecting to Briefly…')).toBeInTheDocument()
  })

  it('shows the empty state when the service is healthy and no stories exist', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, okBody))
    render(<BriefingPage />)
    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
  })

  it('shows a degraded warning when the database is down', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(503, { data: { status: 'degraded', database: 'unavailable', timestamp: 't' } }),
    )
    render(<BriefingPage />)
    expect(await screen.findByText('Service degraded')).toBeInTheDocument()
  })

  it('shows an error with a working retry when the API is unreachable', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(jsonResponse(200, okBody))
    render(<BriefingPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the Briefly server.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
