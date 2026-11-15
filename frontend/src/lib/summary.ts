import type { SummaryPreview } from '../types/api'

export type Basis = { label: string; title: string }

/** Short label describing what the card text is based on, or null for a full-text summary. */
export function summaryBasis(summary: SummaryPreview | null): Basis | null {
  if (summary?.status === 'succeeded') {
    return summary.source_coverage === 'excerpt'
      ? { label: 'Excerpt', title: 'AI summary based only on the publisher’s short excerpt, not the full article' }
      : null
  }
  if (summary?.status === 'insufficient_content') {
    return { label: 'Teaser only', title: 'The publisher’s feed has too little text for an AI summary' }
  }
  return { label: 'Summary pending', title: 'An AI summary hasn’t been generated yet; showing the publisher’s description' }
}
