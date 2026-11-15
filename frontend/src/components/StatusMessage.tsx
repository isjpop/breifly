import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'

type Variant = 'loading' | 'empty' | 'error'

interface StatusMessageProps {
  variant: Variant
  title: string
  children?: ReactNode
  onRetry?: () => void
}

const ICONS = { loading: Loader2, empty: Inbox, error: AlertTriangle } as const

/** Shared loading / empty / error presentation so every view handles these states the same way. */
export function StatusMessage({ variant, title, children, onRetry }: StatusMessageProps) {
  const Icon = ICONS[variant]
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      aria-live="polite"
      className="flex flex-col items-start gap-2 border border-line bg-surface px-5 py-6"
    >
      <div className="flex items-center gap-2">
        <Icon
          size={16}
          aria-hidden
          className={
            variant === 'loading' ? 'animate-spin text-muted' : variant === 'error' ? 'text-negative' : 'text-muted'
          }
        />
        <p className="text-sm font-medium">{title}</p>
      </div>
      {children && <div className="text-sm text-muted">{children}</div>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 text-sm font-medium text-accent underline-offset-4 hover:underline"
        >
          Try again
        </button>
      )}
    </div>
  )
}
