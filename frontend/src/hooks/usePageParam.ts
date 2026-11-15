import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Read/write a single URL search parameter, keeping the others. Empty values are removed. */
export function useSearchParam(name: string, fallback = ''): [string, (value: string, reset?: string[]) => void] {
  const [params, setParams] = useSearchParams()
  const value = params.get(name) ?? fallback
  const setValue = useCallback(
    (next: string, reset: string[] = []) => {
      setParams((current) => {
        const updated = new URLSearchParams(current)
        if (next && next !== fallback) updated.set(name, next)
        else updated.delete(name)
        for (const key of reset) updated.delete(key)
        return updated
      })
    },
    [name, fallback, setParams],
  )
  return [value, setValue]
}

export function parsePage(value: string): number {
  const page = Number.parseInt(value, 10)
  return Number.isFinite(page) && page > 0 ? page : 1
}
