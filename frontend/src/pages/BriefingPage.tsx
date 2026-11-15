import { StatusMessage } from '../components/StatusMessage'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

/**
 * Daily briefing. During the foundation milestone this verifies end-to-end connectivity
 * (browser → Vite → Flask → PostgreSQL); story sections arrive with the briefing API.
 */
export function BriefingPage() {
  const health = useAsync((signal) => api.health(signal).then((r) => r.data), [])

  return (
    <section aria-labelledby="briefing-heading" className="space-y-4">
      <h1 id="briefing-heading" className="font-serif text-2xl font-semibold tracking-tight">
        Today&rsquo;s briefing
      </h1>

      {health.status === 'loading' && <StatusMessage variant="loading" title="Connecting to Briefly…" />}

      {health.status === 'error' && (
        <StatusMessage variant="error" title="Briefly is unreachable" onRetry={health.reload}>
          {health.error.message}
        </StatusMessage>
      )}

      {health.status === 'success' && health.data.status === 'degraded' && (
        <StatusMessage variant="error" title="Service degraded" onRetry={health.reload}>
          The API is running but the database is unavailable.
        </StatusMessage>
      )}

      {health.status === 'success' && health.data.status === 'ok' && (
        <StatusMessage variant="empty" title="No stories yet">
          The service is online. Stories will appear here once news ingestion has run.
        </StatusMessage>
      )}
    </section>
  )
}
