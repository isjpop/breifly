const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' })

/** "just now", "12 min ago", "3 hr ago", "yesterday", or a short date beyond a week. */
export function formatRelative(iso: string, now: Date): string {
  const then = new Date(iso)
  const diff = then.getTime() - now.getTime()
  const abs = Math.abs(diff)
  if (Number.isNaN(abs)) return ''
  if (abs < MINUTE) return 'just now'
  if (abs < HOUR) return relative.format(Math.round(diff / MINUTE), 'minute')
  if (abs < DAY) return relative.format(Math.round(diff / HOUR), 'hour')
  if (abs < 7 * DAY) return relative.format(Math.round(diff / DAY), 'day')
  return formatDate(iso)
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(iso),
  )
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

export function formatLongDate(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}
