import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { Layout } from './Layout'

function Probe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname + location.search}</p>
}

function renderLayout(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <Probe />
      </Layout>
    </MemoryRouter>,
  )
}

describe('Layout', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('toggles the dark class on <html> and persists the choice', async () => {
    renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('briefly-theme')).toBe('dark')

    await userEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('marks the current section in the navigation', () => {
    renderLayout('/category/science')
    const nav = screen.getByRole('navigation', { name: 'Sections' })
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent('Science')
  })

  it('searches from the header', async () => {
    renderLayout()
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search articles' }), 'fusion energy{Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent('/search?q=fusion%20energy')
  })

  it('offers a skip link to the main content', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main')
  })
})
