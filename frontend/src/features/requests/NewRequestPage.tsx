import { Link, useNavigate } from 'react-router'
import { RequestForm } from './components/RequestForm'

export function NewRequestPage() {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col gap-4">
      <Link to="/" className="text-sm underline">
        Back to my requests
      </Link>
      <h1 className="text-2xl font-semibold">New request</h1>
      <p className="text-sm text-muted-foreground">
        Write it the way you would in an email. The system reads the details and checks them against
        company rules.
      </p>
      <RequestForm onSubmitted={(id) => navigate(`/requests/${id}`)} />
    </div>
  )
}
