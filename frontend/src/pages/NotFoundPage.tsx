import { Link } from 'react-router-dom'
import { StatusMessage } from '../components/StatusMessage'

export function NotFoundPage() {
  return (
    <StatusMessage variant="empty" title="Page not found">
      <Link to="/" className="text-accent underline-offset-4 hover:underline">
        Back to today&rsquo;s briefing
      </Link>
    </StatusMessage>
  )
}
