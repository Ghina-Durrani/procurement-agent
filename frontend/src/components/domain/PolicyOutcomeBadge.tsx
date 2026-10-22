import { CheckCircle2, OctagonX, UserSearch } from 'lucide-react'
import { cn } from '@/lib/utils'

export type PolicyOutcome = 'CONTINUE' | 'BLOCK' | 'HUMAN_REVIEW'

const OUTCOME_STYLES = {
  CONTINUE: {
    label: 'Continue',
    Icon: CheckCircle2,
    className: 'bg-outcome-continue-bg text-outcome-continue',
  },
  BLOCK: { label: 'Blocked', Icon: OctagonX, className: 'bg-outcome-block-bg text-outcome-block' },
  HUMAN_REVIEW: {
    label: 'Human review',
    Icon: UserSearch,
    className: 'bg-outcome-review-bg text-outcome-review',
  },
} as const

type PolicyOutcomeBadgeProps = { outcome: PolicyOutcome; className?: string }

/** Shows the deterministic policy outcome. Text + icon, so colour is never the only signal. */
export function PolicyOutcomeBadge({ outcome, className }: PolicyOutcomeBadgeProps) {
  const { label, Icon, className: tone } = OUTCOME_STYLES[outcome]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium',
        tone,
        className,
      )}
    >
      <Icon aria-hidden className="size-4" />
      {label}
    </span>
  )
}
