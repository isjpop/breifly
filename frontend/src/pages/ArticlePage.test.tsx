import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeDetail } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import { renderAt } from '../test/render'
import { ArticlePage } from './ArticlePage'

const ID = '11111111-1111-1111-1111-111111111111'
const route = [{ path: '/article/:id', element: <ArticlePage /> }]

describe('ArticlePage', () => {
  it('shows a loading state', () => {
    mockApi({ [`/api/articles/${ID}`]: 'pending' })
    renderAt(`/article/${ID}`, route)
    expect(screen.getByRole('status')).toHaveTextContent('Loading article')
  })

  it('renders the full summary, attribution, entities and related coverage', async () => {
    const detail = makeDetail({
      id: ID,
      title: 'Original headline',
      url: 'https://publisher.example.com/original',
      related: [
        {
          id: '22222222-2222-2222-2222-222222222222',
          title: 'Other outlet’s take',
          url: 'https://other.example.com/a',
          source: { slug: 'techdesk', name: 'Tech Desk' },
          published_at: null,
        },
      ],
    })
    mockApi({ [`/api/articles/${ID}`]: { body: { data: detail } } })
    renderAt(`/article/${ID}`, route)

    expect(await screen.findByRole('heading', { level: 1, name: 'Original headline' })).toBeInTheDocument()
    expect(screen.getByText('Jane Reporter')).toBeInTheDocument()

    const original = screen.getByRole('link', { name: /Read the full story at Global Wire/ })
    expect(original).toHaveAttribute('href', 'https://publisher.example.com/original')
    expect(original).toHaveAttribute('target', '_blank')
    expect(original).toHaveAttribute('rel', 'noopener noreferrer')

    const takeaways = screen.getByRole('region', { name: 'Key takeaways' })
    expect(within(takeaways).getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText('It matters because of reasons.')).toBeInTheDocument()
    expect(screen.getByText(/gemini-3.5-flash-lite/)).toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'Acme Corp' })).toHaveAttribute('href', '/search?q=%22Acme%20Corp%22')

    const related = screen.getByRole('region', { name: 'Also covered by' })
    expect(within(related).getByRole('link', { name: 'Other outlet’s take' })).toHaveAttribute(
      'href',
      '/article/22222222-2222-2222-2222-222222222222',
    )
  })

  it('explains when no AI summary is available', async () => {
    mockApi({
      [`/api/articles/${ID}`]: {
        body: {
          data: makeDetail({
            id: ID,
            description: 'Publisher teaser.',
            summary: {
              status: 'insufficient_content',
              headline: null,
              bullet_points: [],
              why_it_matters: null,
              source_coverage: null,
              limitations: 'The publisher’s feed provides only a headline',
              key_entities: [],
              model_name: null,
              generated_at: null,
            },
          }),
        },
      },
    })
    renderAt(`/article/${ID}`, route)
    expect(await screen.findByRole('region', { name: 'From the publisher' })).toHaveTextContent('Publisher teaser.')
    expect(screen.getByText('The publisher’s feed provides only a headline')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Key takeaways' })).not.toBeInTheDocument()
  })

  it('labels excerpt-based summaries on the detail page', async () => {
    const detail = makeDetail({ id: ID })
    mockApi({
      [`/api/articles/${ID}`]: { body: { data: { ...detail, summary: { ...detail.summary!, source_coverage: 'excerpt' } } } },
    })
    renderAt(`/article/${ID}`, route)
    expect(await screen.findByText('Based only on the publisher’s excerpt, not the full article.')).toBeInTheDocument()
  })

  it('shows not found for unknown or malformed ids', async () => {
    mockApi({})
    renderAt(`/article/${ID}`, route)
    expect(await screen.findByText('We couldn’t find that page')).toBeInTheDocument()
  })

  it('shows other errors with a retry', async () => {
    mockApi({ [`/api/articles/${ID}`]: { status: 503, body: { error: { code: 'database_unavailable', message: 'Down.' } } } })
    renderAt(`/article/${ID}`, route)
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load this article')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('hides the original link when the URL is unsafe', async () => {
    mockApi({ [`/api/articles/${ID}`]: { body: { data: makeDetail({ id: ID, url: 'javascript:alert(1)' }) } } })
    renderAt(`/article/${ID}`, route)
    expect(await screen.findByText('The original link is unavailable.')).toBeInTheDocument()
  })
})
