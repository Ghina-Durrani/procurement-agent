import { apiRequest } from '@/lib/api-client'
import type { components } from '@/types/api.generated'

export type ReviewItem = components['schemas']['ReviewItem']
export type ReviewQueue = components['schemas']['ReviewQueue']
export type ReviewDecision = components['schemas']['ReviewDecisionIn']

const PATH = '/api/v1/reviews'

export function getReviewQueue(): Promise<ReviewQueue> {
  return apiRequest<ReviewQueue>(PATH)
}

export function decideReview(approvalId: string, body: ReviewDecision): Promise<ReviewQueue> {
  return apiRequest<ReviewQueue>(`${PATH}/${encodeURIComponent(approvalId)}/decision`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
