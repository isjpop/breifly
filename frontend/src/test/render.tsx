import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

/** Exposes the current location so tests can assert on navigation. */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

export function renderAt(path: string, routes: Array<{ path: string; element: ReactElement }>) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        {routes.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
        <Route path="*" element={<div>other page</div>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}
