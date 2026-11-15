import { Search } from 'lucide-react'
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'
import { CATEGORIES, categoryPath } from '../lib/categories'
import { ThemeToggle } from './ThemeToggle'

const NAV_ITEMS = [{ to: '/', label: 'Briefing' }, ...CATEGORIES.map((c) => ({ to: categoryPath(c.slug), label: c.label }))]

export function Layout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme()
  const navRef = useRef<HTMLUListElement>(null)
  const { pathname } = useLocation()

  // On narrow screens the section list scrolls horizontally; keep the active section visible.
  useEffect(() => {
    const active = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')
    active?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [pathname])

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 pt-3 sm:px-6">
          <Link to="/" className="flex items-baseline gap-2.5" aria-label="Briefly home">
            <span className="font-serif text-[1.35rem] font-bold tracking-tight">Briefly</span>
            <span className="hidden text-xs text-muted md:inline">Get informed, not overwhelmed.</span>
          </Link>
          <div className="flex items-center gap-2">
            <HeaderSearch />
            <Link
              to="/search"
              aria-label="Search"
              className="inline-flex h-8 w-8 items-center justify-center border border-line text-muted hover:text-ink sm:hidden"
            >
              <Search size={16} aria-hidden />
            </Link>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </div>
        <nav aria-label="Sections" className="mx-auto max-w-6xl px-4 sm:px-6">
          {/* The right-edge fade signals that the list scrolls on narrow screens. */}
          <ul
            ref={navRef}
            className="-mb-px flex gap-5 overflow-x-auto pr-6 pt-2 text-sm [mask-image:linear-gradient(to_right,black_85%,transparent)] [scrollbar-width:none] md:[mask-image:none]"
          >
            {NAV_ITEMS.map((item) => (
              <li key={item.to} className="shrink-0">
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `block border-b-2 pb-2 transition-colors ${
                      isActive ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:text-ink'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {children}
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl space-y-1 px-4 py-5 text-xs text-muted sm:px-6">
          <p>
            Summaries are AI-generated from publisher feeds and may contain errors. Each story links to its
            original publisher; read it for the full report.
          </p>
          <p>Importance blends real-world impact, significance, source credibility and recency.</p>
        </div>
      </footer>
    </div>
  )
}

function HeaderSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (q.length >= 2) {
      navigate(`/search?q=${encodeURIComponent(q)}`)
      setQuery('')
    }
  }

  return (
    <form role="search" onSubmit={submit} className="relative hidden sm:block">
      <label htmlFor="header-search" className="sr-only">
        Search articles
      </label>
      <Search size={14} aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
      <input
        id="header-search"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search companies, topics…"
        className="h-8 w-56 border border-line bg-canvas pl-8 pr-2 text-sm placeholder:text-muted focus:border-ink/40 focus:outline-none lg:w-64"
      />
    </form>
  )
}
