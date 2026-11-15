import { vi } from 'vitest'

type Reply = { status?: number; body: unknown } | ((url: URL) => { status?: number; body: unknown })

/**
 * Route fetch() by URL pathname. Each call is recorded so tests can assert on query params.
 * A path mapped to a pending promise ('pending') never resolves (for loading states).
 */
export function mockApi(routes: Record<string, Reply | 'pending' | Error>) {
  const calls: URL[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = new URL(String(input), 'http://localhost')
    calls.push(url)
    const route = routes[url.pathname]
    if (route === undefined) return json(404, { error: { code: 'not_found', message: 'Not found.' } })
    if (route === 'pending') return new Promise<Response>(() => {})
    if (route instanceof Error) throw route
    const reply = typeof route === 'function' ? route(url) : route
    return json(reply.status ?? 200, reply.body)
  })
  return {
    calls,
    lastCall: (path: string) => [...calls].reverse().find((u) => u.pathname === path),
  }
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
