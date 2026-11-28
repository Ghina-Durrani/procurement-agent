import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from '@/lib/api-client'
import { type ReviewDecision, type ReviewQueue, decideReview, getReviewQueue } from './api'

export const reviewKeys = { queue: ['reviews'] as const }

export function useReviewQueue() {
  return useQuery<ReviewQueue, ApiError>({ queryKey: reviewKeys.queue, queryFn: getReviewQueue })
}

export function useDecideReview(approvalId: string) {
  const queryClient = useQueryClient()
  return useMutation<ReviewQueue, ApiError, ReviewDecision>({
    mutationFn: (body) => decideReview(approvalId, body),
    onSuccess: (queue) => {
      // The server returns the updated queue; request pages are stale after a decision.
      queryClient.setQueryData(reviewKeys.queue, queue)
      void queryClient.invalidateQueries({ queryKey: ['requests'] })
    },
  })
}
