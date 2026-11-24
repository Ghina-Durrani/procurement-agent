import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { RequestList } from './components/RequestList'
import { useMyRequests } from './hooks'

export function MyRequestsPage() {
  const requests = useMyRequests()
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">My requests</h1>
        <Button asChild>
          <Link to="/requests/new">New request</Link>
        </Button>
      </div>
      {requests.isPending && (
        <div aria-label="Loading requests" className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}
      {requests.isError && (
        <p role="alert" className="text-destructive">
          Could not load your requests. {requests.error.message}
        </p>
      )}
      {requests.isSuccess && requests.data.items.length === 0 && (
        <p>You have not submitted any requests yet.</p>
      )}
      {requests.isSuccess && requests.data.items.length > 0 && (
        <RequestList items={requests.data.items} />
      )}
    </div>
  )
}
