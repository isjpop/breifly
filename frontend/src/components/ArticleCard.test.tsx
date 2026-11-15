import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { makeArticle } from '../test/fixtures'
import type { ArticleCardData } from '../types/api'
import { ArticleCard, type CardVariant } from './ArticleCard'

function renderCard(article: ArticleCardData, variant: CardVariant = 'standard') {
  return render(
    <MemoryRouter>
      <ArticleCard article={article} variant={variant} />
    </MemoryRouter>,
  )
}

describe('ArticleCard', () => {
  it('renders headline, publisher, category, importance and up to three takeaways', () => {
    const article = makeArticle({ title: 'Fed cuts rates', importance_score: 8.2 })
    renderCard(article)

    const card = screen.getByRole('article', { name: 'Fed cuts rates' })
    expect(within(card).getByRole('link', { name: 'Fed cuts rates' })).toHaveAttribute('href', `/article/${article.id}`)
    expect(within(card).getByText('Global Wire')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Finance' })).toHaveAttribute('href', '/category/finance')
    expect(within(card).getByRole('img', { name: 'Importance 8.2 out of 10' })).toBeInTheDocument()
    expect(within(card).getAllByRole('listitem')).toHaveLength(3)
    expect(within(card).queryByText('Fourth takeaway.')).not.toBeInTheDocument()
  })

  it('links to the original publisher in a new tab without leaking the opener', () => {
    renderCard(makeArticle({ url: 'https://publisher.example.com/a' }))
    const link = screen.getByRole('link', { name: /Original/ })
    expect(link).toHaveAttribute('href', 'https://publisher.example.com/a')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveTextContent('opens publisher site in a new tab')
  })

  it('never renders an unsafe original link', () => {
    renderCard(makeArticle({ url: 'javascript:alert(1)' }))
    expect(screen.queryByRole('link', { name: /Original/ })).not.toBeInTheDocument()
  })

  it('labels excerpt-based summaries', () => {
    const base = makeArticle()
    renderCard({ ...base, summary: { ...base.summary!, source_coverage: 'excerpt' } })
    expect(screen.getByText('Excerpt')).toBeInTheDocument()
  })

  it('falls back to the publisher description when no summary exists', () => {
    renderCard(makeArticle({ summary: null, description: 'Teaser text.' }))
    expect(screen.getByText('Teaser text.')).toBeInTheDocument()
    expect(screen.getByText('Summary pending')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('explains when the feed is too thin to summarize', () => {
    renderCard(
      makeArticle({
        summary: {
          status: 'insufficient_content',
          headline: null,
          bullet_points: [],
          why_it_matters: null,
          source_coverage: null,
          limitations: 'Headline only',
        },
      }),
    )
    expect(screen.getByText('Teaser only')).toBeInTheDocument()
  })

  it('adds “why it matters” to the lead story only', () => {
    const article = makeArticle()
    const { unmount } = renderCard(article, 'standard')
    expect(screen.queryByText(/Why it matters/)).not.toBeInTheDocument()
    unmount()
    renderCard(article, 'lead')
    expect(screen.getByText('It matters because of reasons.')).toBeInTheDocument()
  })

  it('shows related coverage and only renders the image on the lead variant', () => {
    const article = makeArticle({ related_count: 2, image_url: 'https://cdn.example.com/a.jpg' })
    const { container, unmount } = renderCard(article, 'standard')
    expect(screen.getByRole('link', { name: '+2 sources' })).toHaveAttribute('href', `/article/${article.id}`)
    expect(container.querySelector('img')).toBeNull()
    unmount()

    const lead = renderCard(article, 'lead')
    expect(lead.container.querySelector('img')).toHaveAttribute('referrerpolicy', 'no-referrer')
  })
})
