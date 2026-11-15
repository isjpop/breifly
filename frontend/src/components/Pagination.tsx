import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { Pagination as PaginationData } from '../types/api'

interface PaginationProps {
  pagination: PaginationData
  onPageChange: (page: number) => void
}

export function Pagination({ pagination, onPageChange }: PaginationProps) {
  const { page, total_pages: totalPages, total } = pagination
  if (totalPages <= 1) return null
  const button =
    'inline-flex items-center gap-1 border border-line px-3 py-1.5 text-sm transition-colors hover:border-ink/40 disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between border-t border-line pt-4">
      <button type="button" className={button} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft size={14} aria-hidden /> Previous
      </button>
      <p className="text-xs text-muted">
        Page <span className="font-mono">{page}</span> of <span className="font-mono">{totalPages}</span>
        <span className="hidden sm:inline"> · {total} articles</span>
      </p>
      <button
        type="button"
        className={button}
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Next <ChevronRight size={14} aria-hidden />
      </button>
    </nav>
  )
}
