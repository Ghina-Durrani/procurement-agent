import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderAt } from '@/test/render'
import { API, aRequest } from '@/test/requests-data'
import { server } from '@/test/server'

const ANSWER_URL = `${API}/${aRequest().id}/clarifications`

describe('Follow-up questions', () => {
  it('shows the open question and sends the exact answer', async () => {
    const request = aRequest()
    const answered = aRequest({
      status: 'APPROVED',
      outcome: 'CONTINUE',
      missing_fields: [],
      clarifications: [
        {
          ...request.clarifications[0],
          answer: '  Rs 30,000 total ',
          answered_at: '2026-11-24T10:05:00Z',
        },
      ],
    })
    let sent: unknown = null
    server.use(
      http.get(`${API}/${request.id}`, () => HttpResponse.json(request)),
      http.post(ANSWER_URL, async ({ request: sentRequest }) => {
        sent = await sentRequest.json()
        return HttpResponse.json(answered)
      }),
    )
    renderAt(`/requests/${request.id}`)

    expect(
      await screen.findByText('What is the estimated total cost of the whole request?'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Round 1 of 2/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Your answer'), '  Rs 30,000 total ')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))

    expect(await screen.findByText('Approved')).toBeInTheDocument()
    expect(sent).toEqual({ answer: '  Rs 30,000 total ' })
    // The round is answered: its answer is shown and the form is gone.
    expect(screen.queryByRole('button', { name: 'Send answer' })).not.toBeInTheDocument()
  })

  it('refuses a blank answer without calling the server', async () => {
    const request = aRequest()
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    renderAt(`/requests/${request.id}`) // no POST handler: any call would fail the test
    await userEvent.click(await screen.findByRole('button', { name: 'Send answer' }))
    expect(await screen.findByText('Write your answer.')).toBeInTheDocument()
  })

  it('warns on the last round', async () => {
    const request = aRequest({
      clarifications: [
        {
          ...aRequest().clarifications[0],
          answer: 'Not sure yet.',
          answered_at: '2026-11-24T10:05:00Z',
        },
        { ...aRequest().clarifications[0], round_number: 2 },
      ],
    })
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    renderAt(`/requests/${request.id}`)
    expect(await screen.findByText(/This is the last round/)).toBeInTheDocument()
    expect(screen.getByText('Not sure yet.')).toBeInTheDocument()
  })

  it('shows a conflict from the server as a message', async () => {
    const request = aRequest()
    server.use(
      http.get(`${API}/${request.id}`, () => HttpResponse.json(request)),
      http.post(ANSWER_URL, () =>
        HttpResponse.json(
          {
            code: 'CONFLICT',
            message: 'This request is not waiting for more details.',
            field_errors: null,
          },
          { status: 409 },
        ),
      ),
    )
    renderAt(`/requests/${request.id}`)
    await userEvent.type(await screen.findByLabelText('Your answer'), 'Rs 30,000')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This request is not waiting for more details.',
    )
  })

  it('shows an answer as text, never as HTML, and no form once a person reviews', async () => {
    const request = aRequest({
      status: 'AWAITING_APPROVAL',
      clarifications: [
        {
          ...aRequest().clarifications[0],
          answer: '<img src=x onerror="alert(1)">',
          answered_at: '2026-11-24T10:05:00Z',
        },
      ],
    })
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    const { container } = renderAt(`/requests/${request.id}`)
    expect(await screen.findByText('<img src=x onerror="alert(1)">')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Send answer' })).not.toBeInTheDocument()
  })
})

describe('Reviews on the request page', () => {
  it('shows who decided and their comment', async () => {
    const request = aRequest({
      status: 'REJECTED',
      clarifications: [],
      approvals: [
        {
          required_role: 'MANAGER',
          decision: 'REJECTED',
          decided_by: 'Demo Manager',
          decided_at: '2026-11-28T10:00:00Z',
          comment: 'Use the existing chairs.',
        },
      ],
    })
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    renderAt(`/requests/${request.id}`)
    expect(await screen.findByText(/Rejected by Demo Manager/)).toBeInTheDocument()
    expect(screen.getByText('Use the existing chairs.')).toBeInTheDocument()
  })
})
