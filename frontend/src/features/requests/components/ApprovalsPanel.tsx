import type { ApprovalItem } from '../api'
import { formatDate } from '../labels'

const DECISION_TEXT: Record<ApprovalItem['decision'], string> = {
  PENDING: 'Waiting',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
}

/** Who must review the request and what they decided (D-065). Comments are plain text. */
export function ApprovalsPanel({ approvals }: { approvals: ApprovalItem[] }) {
  return (
    <section aria-labelledby="approvals-heading" className="flex flex-col gap-3">
      <h2 id="approvals-heading" className="text-lg font-semibold">
        Reviews
      </h2>
      <ul className="flex flex-col gap-2">
        {approvals.map((approval, index) => (
          <li key={`${approval.required_role}-${index}`} className="rounded-lg border p-3">
            <p>
              <span className="font-medium">{approval.required_role}</span>:{' '}
              {DECISION_TEXT[approval.decision]}
              {approval.decided_by && ` by ${approval.decided_by}`}
              {approval.decided_at && ` on ${formatDate(approval.decided_at)}`}
            </p>
            {approval.comment && (
              <p className="break-words whitespace-pre-wrap text-sm">{approval.comment}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
