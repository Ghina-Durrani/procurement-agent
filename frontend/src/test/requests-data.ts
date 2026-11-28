import type { components } from '@/types/api.generated'

type RequestDetail = components['schemas']['RequestDetail']

export const API = 'http://127.0.0.1:8000/api/v1/requests'

export function aRequest(changes: Partial<RequestDetail> = {}): RequestDetail {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    status: 'NEEDS_CLARIFICATION',
    message: 'Need 3 office chairs from Metro Furniture for the new meeting room.',
    submitted_at: '2026-11-24T10:00:00Z',
    outcome: 'HUMAN_REVIEW',
    proposed_priority: 'NORMAL',
    extraction_status: 'INVALID',
    missing_fields: ['estimated_total'],
    fields: [
      { name: 'item_description', status: 'PRESENT', value: 'office chairs' },
      { name: 'estimated_total', status: 'MISSING', value: null },
    ],
    read_by: 'fake (development cases only)',
    decision: {
      outcome: 'HUMAN_REVIEW',
      triggered_rules: [
        {
          rule_id: 'POL-001',
          outcome: 'HUMAN_REVIEW',
          reason: 'Missing required fields: estimated_total.',
          required_approver_role: null,
        },
      ],
      required_approver_roles: [],
      policy_version: 'demo-2026-11-05.1',
      evaluated_at: '2026-11-24T10:00:01Z',
    },
    clarifications: [
      {
        round_number: 1,
        questions: [
          {
            field: 'estimated_total',
            question: 'What is the estimated total cost of the whole request?',
          },
        ],
        answer: null,
        asked_at: '2026-11-24T10:00:01Z',
        answered_at: null,
      },
    ],
    max_clarification_rounds: 2,
    ...changes,
  }
}
