import { Link } from 'react-router'
import { PolicyOutcomeBadge } from '@/components/domain/PolicyOutcomeBadge'
import type { RequestSummary } from '../api'
import { STATUS_TEXT, formatDate } from '../labels'

type RequestListProps = { items: RequestSummary[] }

export function RequestList({ items }: RequestListProps) {
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.id} className="rounded-lg border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">{formatDate(item.submitted_at)}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{STATUS_TEXT[item.status].label}</span>
              {item.outcome && <PolicyOutcomeBadge outcome={item.outcome} />}
            </div>
          </div>
          {/* Untrusted text: rendered as plain text, shortened by CSS only. */}
          <p className="mt-2 line-clamp-2 break-words">{item.message}</p>
          <Link to={`/requests/${item.id}`} className="mt-2 inline-block text-sm underline">
            View details
          </Link>
        </li>
      ))}
    </ul>
  )
}
