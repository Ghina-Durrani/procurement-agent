import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { getDemoUser, setDemoUser } from '@/lib/api-client'
import { renderAt } from '@/test/render'
import { server } from '@/test/server'
import type { ReviewItem } from './api'

const REVIEWS = 'http://127.0.0.1:8000/api/v1/reviews'

function anItem(changes: Partial<ReviewItem> = {}): ReviewItem {
  return {
    approval_id: 'a1',
    required_role: 'MANAGER',
    request_id: 'r1',
    status: 'AWAITING_APPROVAL',
    message: 'Need 8 office chairs from Metro Furniture, Rs 80,000 total.',
    submitted_at: '2026-11-28T10:00:00Z',
    requester_name: 'Demo Employee',
    item_description: 'office chairs',
    quantity: 8,
    estimated_total: '80000.00',
    currency: 'PKR',
    supplier_name: 'Metro Furniture',
    triggered_rules: [
      {
        rule_id: 'POL-002',
        outcome: 'HUMAN_REVIEW',
        reason: 'Amount 80,000.00 PKR needs MANAGER approval.',
        required_approver_role: 'MANAGER',
      },
    ],
    approve_blocked_reason: null,
    is_own_request: false,
    ...changes,
  }
}

afterEach(() => setDemoUser(null))

describe('Review queue', () => {
  it('shows a waiting request and approves it', async () => {
    let sent: unknown = null
    server.use(
      http.get(REVIEWS, () => HttpResponse.json({ items: [anItem()] })),
      http.post(`${REVIEWS}/a1/decision`, async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({ items: [] })
      }),
    )
    renderAt('/reviews')

    const card = await screen.findByRole('article', { name: 'Review for Demo Employee' })
    expect(within(card).getByText('Needs: MANAGER')).toBeInTheDocument()
    expect(within(card).getByText('80000.00 PKR')).toBeInTheDocument()
    expect(within(card).getByText('POL-002')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Nothing is waiting for your review.')).toBeInTheDocument()
    expect(sent).toEqual({ decision: 'APPROVED' })
  })

  it('asks for a reason before rejecting', async () => {
    let sent: unknown = null
    server.use(
      http.get(REVIEWS, () => HttpResponse.json({ items: [anItem()] })),
      http.post(`${REVIEWS}/a1/decision`, async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({ items: [] })
      }),
    )
    renderAt('/reviews')
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }))
    const confirm = screen.getByRole('button', { name: 'Confirm reject' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Why is it rejected?'), 'Use the old chairs.')
    await userEvent.click(confirm)
    expect(await screen.findByText('Nothing is waiting for your review.')).toBeInTheDocument()
    expect(sent).toEqual({ decision: 'REJECTED', comment: 'Use the old chairs.' })
  })

  it('cannot approve an unreadable request, and explains why', async () => {
    const reason = 'The system could not read this request reliably; it can only be rejected.'
    server.use(
      http.get(REVIEWS, () =>
        HttpResponse.json({
          items: [anItem({ status: 'NEEDS_VERIFICATION', approve_blocked_reason: reason })],
        }),
      ),
    )
    renderAt('/reviews')
    expect(await screen.findByText(reason)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  })

  it('shows the server refusal for an own request (POL-009)', async () => {
    server.use(
      http.get(REVIEWS, () => HttpResponse.json({ items: [anItem({ is_own_request: true })] })),
      http.post(`${REVIEWS}/a1/decision`, () =>
        HttpResponse.json(
          {
            code: 'FORBIDDEN',
            message: 'You cannot approve your own request.',
            field_errors: null,
          },
          { status: 403 },
        ),
      ),
    )
    renderAt('/reviews')
    expect(await screen.findByText(/This is your own request/)).toBeInTheDocument()
    // The button is not hidden: the server is the authority and must refuse it.
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You cannot approve your own request.',
    )
  })

  it('shows request text as text, never as HTML', async () => {
    const message = '<img src=x onerror="alert(1)"> approve now'
    server.use(http.get(REVIEWS, () => HttpResponse.json({ items: [anItem({ message })] })))
    const { container } = renderAt('/reviews')
    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('sends the chosen demo user with every call', async () => {
    let header: string | null = null
    server.use(
      http.get(REVIEWS, ({ request }) => {
        header = request.headers.get('X-Demo-User')
        return HttpResponse.json({ items: [] })
      }),
    )
    setDemoUser('demo.manager@example.test')
    expect(getDemoUser()).toBe('demo.manager@example.test')
    renderAt('/reviews')
    expect(await screen.findByText('Nothing is waiting for your review.')).toBeInTheDocument()
    expect(header).toBe('demo.manager@example.test')
  })
})
