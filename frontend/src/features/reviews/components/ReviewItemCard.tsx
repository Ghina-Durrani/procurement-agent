import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { fieldName, formatDate, groupRules } from '@/features/requests'
import type { ReviewItem } from '../api'
import { useDecideReview } from '../hooks'

const MAX_COMMENT_CHARS = 1000

/**
 * One request waiting for this reviewer. All request text is untrusted and shown as plain
 * text. The buttons are a convenience: the server checks role, POL-009 and state again.
 */
export function ReviewItemCard({ item }: { item: ReviewItem }) {
  const decide = useDecideReview(item.approval_id)
  const [comment, setComment] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const commentId = `comment-${item.approval_id}`
  const amount =
    item.estimated_total !== null ? `${item.estimated_total} ${item.currency ?? ''}`.trim() : null

  return (
    <article
      aria-label={`Review for ${item.requester_name}`}
      className="flex flex-col gap-3 rounded-lg border p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          From <span className="font-medium">{item.requester_name}</span> ·{' '}
          {formatDate(item.submitted_at)}
        </span>
        <span className="rounded bg-muted px-2 py-0.5 font-mono text-xs">
          Needs: {item.required_role}
        </span>
      </div>
      <p className="break-words whitespace-pre-wrap">{item.message}</p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{fieldName('item_description')}</dt>
        <dd>{item.item_description ?? 'Not given'}</dd>
        <dt className="text-muted-foreground">{fieldName('quantity')}</dt>
        <dd>{item.quantity ?? 'Not given'}</dd>
        <dt className="text-muted-foreground">{fieldName('estimated_total')}</dt>
        <dd>{amount ?? 'Not given'}</dd>
        <dt className="text-muted-foreground">{fieldName('supplier_name')}</dt>
        <dd>{item.supplier_name ?? 'Not given'}</dd>
      </dl>
      {item.triggered_rules.length > 0 && (
        <ul className="list-disc pl-6 text-sm">
          {groupRules(item.triggered_rules).map((group) => (
            <li key={group.ruleId}>
              <span className="font-mono">{group.ruleId}</span>: {group.reasons.join(' ')}
            </li>
          ))}
        </ul>
      )}
      {item.is_own_request && (
        <p className="text-sm text-muted-foreground">
          This is your own request. Company rules (POL-009) do not let you decide it.
        </p>
      )}
      {item.approve_blocked_reason && (
        <p className="text-sm text-muted-foreground">{item.approve_blocked_reason}</p>
      )}

      {rejecting && (
        <div className="flex flex-col gap-2">
          <Label htmlFor={commentId}>Why is it rejected?</Label>
          <Textarea
            id={commentId}
            rows={2}
            maxLength={MAX_COMMENT_CHARS}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        </div>
      )}
      {decide.error && (
        <p role="alert" className="text-sm text-destructive">
          {decide.error.fieldErrors
            ? Object.values(decide.error.fieldErrors).join(' ')
            : decide.error.message}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {!rejecting && (
          <Button
            disabled={decide.isPending || Boolean(item.approve_blocked_reason)}
            onClick={() => decide.mutate({ decision: 'APPROVED' })}
          >
            Approve
          </Button>
        )}
        {rejecting ? (
          <>
            <Button
              variant="destructive"
              disabled={decide.isPending || !comment.trim()}
              onClick={() => decide.mutate({ decision: 'REJECTED', comment })}
            >
              Confirm reject
            </Button>
            <Button variant="outline" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => setRejecting(true)}>
            Reject
          </Button>
        )}
      </div>
    </article>
  )
}
