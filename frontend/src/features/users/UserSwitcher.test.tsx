import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { apiRequest, getDemoUser, setDemoUser } from '@/lib/api-client'
import { server } from '@/test/server'
import { UserSwitcher } from './UserSwitcher'

const BASE = 'http://127.0.0.1:8000/api/v1'
const USERS = [
  { email: 'demo.employee@example.test', full_name: 'Demo Employee', role: 'Requester' },
  {
    email: 'demo.finance@example.test',
    full_name: 'Demo Finance Approver',
    role: 'FINANCE_APPROVER',
  },
  { email: 'demo.manager@example.test', full_name: 'Demo Manager', role: 'MANAGER' },
  {
    email: 'demo.senior.manager@example.test',
    full_name: 'Demo Senior Manager',
    role: 'SENIOR_MANAGER',
  },
]

/** The server answers as whoever the X-Demo-User header names (default: the employee). */
function asHeader(request: Request) {
  const email = request.headers.get('X-Demo-User') ?? USERS[0].email
  return USERS.find((user) => user.email === email)!
}

function WhoAmI() {
  // Stands in for any page: its data must be fetched again as the new user.
  const me = useQuery({
    queryKey: ['page-data'],
    queryFn: () => apiRequest<{ role: string }>('/api/v1/me'),
  })
  return <p>Page loaded as: {me.data?.role ?? '...'}</p>
}

function renderSwitcher() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <UserSwitcher />
      <WhoAmI />
    </QueryClientProvider>,
  )
}

afterEach(() => setDemoUser(null))

describe('User switcher (dev only)', () => {
  it('switches to every user in turn and reloads the page data as that user', async () => {
    server.use(
      http.get(`${BASE}/me`, ({ request }) => HttpResponse.json(asHeader(request))),
      http.get(`${BASE}/dev/users`, () => HttpResponse.json({ users: USERS })),
    )
    renderSwitcher()
    const select = await screen.findByLabelText('Acting as')
    expect(select).toHaveValue('demo.employee@example.test')
    expect(await screen.findByText('Page loaded as: Requester')).toBeInTheDocument()

    for (const user of [USERS[2], USERS[3], USERS[1], USERS[0]]) {
      await userEvent.selectOptions(screen.getByLabelText('Acting as'), user.email)
      expect(await screen.findByText(`Page loaded as: ${user.role}`)).toBeInTheDocument()
      expect(screen.getByLabelText('Acting as')).toHaveValue(user.email)
      expect(getDemoUser()).toBe(user.email)
    }
  })

  it('falls back to the default user when the saved one no longer exists', async () => {
    setDemoUser('deleted@example.test')
    server.use(
      http.get(`${BASE}/me`, ({ request }) =>
        request.headers.get('X-Demo-User') === 'deleted@example.test'
          ? HttpResponse.json(
              { code: 'UNAUTHENTICATED', message: 'Unknown demo user.', field_errors: null },
              { status: 401 },
            )
          : HttpResponse.json(asHeader(request)),
      ),
      http.get(`${BASE}/dev/users`, ({ request }) =>
        request.headers.get('X-Demo-User') === 'deleted@example.test'
          ? HttpResponse.json(
              { code: 'UNAUTHENTICATED', message: 'Unknown demo user.', field_errors: null },
              { status: 401 },
            )
          : HttpResponse.json({ users: USERS }),
      ),
    )
    renderSwitcher()
    expect(await screen.findByLabelText('Acting as')).toHaveValue('demo.employee@example.test')
    expect(getDemoUser()).toBeNull()
  })
})
