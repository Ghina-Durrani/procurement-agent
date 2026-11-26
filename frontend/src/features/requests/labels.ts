import type { Priority, RequestStatus } from './api'

/** Display text for backend values. Wire values stay unchanged; only the UI edge maps them. */
export const STATUS_TEXT: Record<RequestStatus, { label: string; next: string }> = {
  RECEIVED: { label: 'Received', next: 'The request is being checked.' },
  NEEDS_CLARIFICATION: {
    label: 'Needs more details',
    next: 'Some required details are missing. Answering follow-up questions here comes in a later step.',
  },
  NEEDS_VERIFICATION: {
    label: 'Being verified',
    next: 'The system could not read this request reliably, so no details were taken from it. A person will check it.',
  },
  AWAITING_APPROVAL: {
    label: 'Waiting for review',
    next: 'A person must review this request before it can go ahead.',
  },
  BLOCKED: { label: 'Blocked', next: 'This request breaks a company rule and cannot go ahead.' },
  APPROVED: {
    label: 'Approved',
    next: 'No approval was needed under company rules. It can go ahead to sourcing.',
  },
  REJECTED: { label: 'Rejected', next: 'A reviewer rejected this request.' },
  WITHDRAWN: { label: 'Withdrawn', next: 'The request was withdrawn.' },
  QUOTING: { label: 'Collecting quotations', next: 'Suppliers are being asked for prices.' },
  ORDERED: { label: 'Ordered', next: 'A purchase order has been issued.' },
}

export const PRIORITY_TEXT: Record<Priority, string> = {
  NORMAL: 'Normal',
  HIGH_PRIORITY: 'High priority',
  EMERGENCY: 'Emergency (claimed, to be confirmed)',
}

export const FIELD_TEXT: Record<string, string> = {
  item_description: 'Item',
  quantity: 'Quantity',
  unit: 'Unit',
  estimated_total: 'Estimated total',
  currency: 'Currency',
  item_category: 'Category',
  supplier_name: 'Supplier',
  delivery_deadline: 'Needed by',
  delivery_location: 'Delivery location',
  business_justification: 'Reason for buying',
}

export const FIELD_STATUS_TEXT: Record<string, string> = {
  PRESENT: 'Found',
  MISSING: 'Missing',
  AMBIGUOUS: 'Unclear',
  CONFLICTING: 'Conflicting',
}

export function fieldName(name: string): string {
  return FIELD_TEXT[name] ?? name
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export type RuleGroup = { ruleId: string; reasons: string[] }

/** One entry per rule, in the order the engine gave them, with all its reasons together. */
export function groupRules(rules: { rule_id: string; reason: string }[]): RuleGroup[] {
  const groups: RuleGroup[] = []
  for (const rule of rules) {
    const group = groups.find((existing) => existing.ruleId === rule.rule_id)
    if (group) {
      if (!group.reasons.includes(rule.reason)) group.reasons.push(rule.reason)
    } else {
      groups.push({ ruleId: rule.rule_id, reasons: [rule.reason] })
    }
  }
  return groups
}

/** True when nothing usable was read, so per-field details would only mislead. */
export function nothingRead(status: RequestStatus): boolean {
  return status === 'NEEDS_VERIFICATION'
}
