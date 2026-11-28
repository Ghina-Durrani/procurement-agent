import { Link, useParams } from 'react-router'
import { Skeleton } from '@/components/ui/skeleton'
import { ClarificationPanel } from './components/ClarificationPanel'
import { DecisionPanel } from './components/DecisionPanel'
import { FieldTable } from './components/FieldTable'
import { useRequest } from './hooks'
import { formatDate, nothingRead } from './labels'

export function RequestDetailPage() {
  const { id = '' } = useParams()
  const request = useRequest(id)
  return (
    <div className="flex flex-col gap-5">
      <Link to="/" className="text-sm underline">
        Back to my requests
      </Link>
      <h1 className="text-2xl font-semibold">Request details</h1>
      {request.isPending && <Skeleton aria-label="Loading request" className="h-40 w-full" />}
      {request.isError && (
        <p role="alert" className="text-destructive">
          {request.error.code === 'NOT_FOUND'
            ? 'Request not found.'
            : `Could not load this request. ${request.error.message}`}
        </p>
      )}
      {request.isSuccess && (
        <>
          <section aria-labelledby="message-heading" className="flex flex-col gap-2">
            <h2 id="message-heading" className="text-lg font-semibold">
              Your message
            </h2>
            <p className="text-sm text-muted-foreground">
              Sent {formatDate(request.data.submitted_at)}
            </p>
            {/* The original text, exactly as written; plain text only. */}
            <p className="rounded-lg border p-3 break-words whitespace-pre-wrap">
              {request.data.message}
            </p>
          </section>
          <DecisionPanel request={request.data} />
          {request.data.clarifications.length > 0 && <ClarificationPanel request={request.data} />}
          {request.data.fields.length > 0 && !nothingRead(request.data.status) && (
            <section aria-labelledby="fields-heading" className="flex flex-col gap-2">
              <h2 id="fields-heading" className="text-lg font-semibold">
                What the system read
              </h2>
              {request.data.read_by && (
                <p className="text-xs text-muted-foreground">Read by: {request.data.read_by}</p>
              )}
              <FieldTable fields={request.data.fields} />
            </section>
          )}
        </>
      )}
    </div>
  )
}
