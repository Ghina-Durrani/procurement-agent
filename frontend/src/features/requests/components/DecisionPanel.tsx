import { PolicyOutcomeBadge } from '@/components/domain/PolicyOutcomeBadge'
import type { RequestDetail } from '../api'
import {
  PRIORITY_TEXT,
  STATUS_TEXT,
  fieldName,
  formatDate,
  groupRules,
  nothingRead,
} from '../labels'

type DecisionPanelProps = { request: RequestDetail }

/** The policy engine's decision and its reasons. The decision comes from code, not the AI. */
export function DecisionPanel({ request }: DecisionPanelProps) {
  const { decision } = request
  const status = STATUS_TEXT[request.status]
  return (
    <section aria-labelledby="decision-heading" className="flex flex-col gap-3">
      <h2 id="decision-heading" className="text-lg font-semibold">
        Decision
      </h2>
      <div className="flex flex-wrap items-center gap-3">
        {decision ? (
          <PolicyOutcomeBadge outcome={decision.outcome} />
        ) : (
          <span className="text-sm">Not decided yet</span>
        )}
        <span className="font-medium">{status.label}</span>
      </div>
      <p>{status.next}</p>
      {request.proposed_priority && (
        <p className="text-sm">Priority: {PRIORITY_TEXT[request.proposed_priority]}</p>
      )}
      {decision && decision.triggered_rules.length > 0 && (
        <div>
          <h3 className="font-medium">Reasons</h3>
          <ul className="list-disc pl-6">
            {groupRules(decision.triggered_rules).map((group) => (
              <li key={group.ruleId}>
                <span className="font-mono text-sm">{group.ruleId}</span>:{' '}
                {group.reasons.length === 1 ? (
                  group.reasons[0]
                ) : (
                  <ul className="list-[circle] pl-6">
                    {group.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {decision && decision.required_approver_roles.length > 0 && (
        <p className="text-sm">
          Must be reviewed by: {decision.required_approver_roles.join(', ')}
        </p>
      )}
      {request.missing_fields.length > 0 && !nothingRead(request.status) && (
        <p className="text-sm">
          Missing details: {request.missing_fields.map((name) => fieldName(name)).join(', ')}
        </p>
      )}
      {decision && (
        <p className="text-xs text-muted-foreground">
          Checked {formatDate(decision.evaluated_at)}
          {decision.policy_version ? ` against policy ${decision.policy_version}` : ''}.
        </p>
      )}
    </section>
  )
}
