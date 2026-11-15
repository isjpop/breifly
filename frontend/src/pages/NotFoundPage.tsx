import { Link } from 'react-router-dom'
import { StatusMessage } from '../components/StatusMessage'

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl">
      <StatusMessage variant="empty" title="We couldn’t find that page">
        <Link to="/" className="text-accent underline-offset-4 hover:underline">
          Back to today’s briefing
        </Link>
      </StatusMessage>
    </div>
  )
}
