import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** Reset scroll on route changes (not on query-string changes such as sort or filters). */
export function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
  return null
}
