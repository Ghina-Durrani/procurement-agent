import { Skeleton } from '@/components/ui/skeleton'
import { ReviewItemCard } from './components/ReviewItemCard'
import { useReviewQueue } from './hooks'

/** Requests waiting for a decision that the current user's role may make (D-065). */
export function ReviewQueuePage() {
  const queue = useReviewQueue()
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Review queue</h1>
      {queue.isPending && (
        <div aria-label="Loading reviews" className="flex flex-col gap-3">
          <Skeleton className="h-32 w-full" />
        </div>
      )}
      {queue.isError && (
        <p role="alert" className="text-destructive">
          Could not load the review queue. {queue.error.message}
        </p>
      )}
      {queue.isSuccess && queue.data.items.length === 0 && (
        <p>Nothing is waiting for your review.</p>
      )}
      {queue.isSuccess &&
        queue.data.items.map((item) => <ReviewItemCard key={item.approval_id} item={item} />)}
    </div>
  )
}
