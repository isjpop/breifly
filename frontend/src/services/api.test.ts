import { describe, expect, it, vi } from 'vitest'
import { ApiError, api, getJson } from './api'

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(typeof body === 'string' ? body : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('getJson', () => {
  it('unwraps the data envelope on success', async () => {
    mockFetch(200, { data: { value: 1 }, meta: { page: 1 } })
    const result = await getJson<{ value: number }>('/api/x')
    expect(result.data.value).toBe(1)
    expect(result.meta).toEqual({ page: 1 })
  })

  it('raises ApiError with the server error code and message', async () => {
    mockFetch(404, { error: { code: 'not_found', message: 'Article not found.' } })
    await expect(getJson('/api/x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'not_found',
      message: 'Article not found.',
    })
  })

  it('raises a generic ApiError for non-JSON error bodies', async () => {
    mockFetch(502, '<html>Bad gateway</html>')
    await expect(getJson('/api/x')).rejects.toMatchObject({ status: 502, code: 'http_error' })
  })

  it('maps network failures to a friendly ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await getJson('/api/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('network_error')
  })
})

describe('api.health', () => {
  it('returns degraded status instead of throwing on 503', async () => {
    mockFetch(503, { data: { status: 'degraded', database: 'unavailable', timestamp: 't' } })
    const result = await api.health()
    expect(result.data.status).toBe('degraded')
  })
})
