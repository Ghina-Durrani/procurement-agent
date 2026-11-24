import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderAt } from '@/test/render'
import { API, aRequest } from '@/test/requests-data'
import { server } from '@/test/server'

describe('My requests page', () => {
  it('shows loading, then the list with status and outcome', async () => {
    server.use(http.get(API, () => HttpResponse.json({ items: [aRequest()], total: 1 })))
    renderAt('/')
    expect(screen.getByLabelText('Loading requests')).toBeInTheDocument()
    expect(await screen.findByText('Needs more details')).toBeInTheDocument()
    expect(screen.getByText('Human review')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View details' })).toHaveAttribute(
      'href',
      `/requests/${aRequest().id}`,
    )
  })

  it('shows an empty state', async () => {
    server.use(http.get(API, () => HttpResponse.json({ items: [], total: 0 })))
    renderAt('/')
    expect(await screen.findByText('You have not submitted any requests yet.')).toBeInTheDocument()
  })

  it('shows a server error message', async () => {
    server.use(
      http.get(API, () =>
        HttpResponse.json(
          { code: 'UNAUTHENTICATED', message: 'Login is not available yet.', field_errors: null },
          { status: 401 },
        ),
      ),
    )
    renderAt('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('Login is not available yet.')
  })
})

describe('New request page', () => {
  it('refuses a blank message without calling the server', async () => {
    renderAt('/requests/new') // no handler: any request would fail the test
    await userEvent.click(screen.getByRole('button', { name: 'Submit request' }))
    expect(await screen.findByText('Write what you need to buy.')).toBeInTheDocument()
  })

  it('submits the exact text and opens the result', async () => {
    let sent: unknown = null
    const created = aRequest({ status: 'APPROVED', outcome: 'CONTINUE', missing_fields: [] })
    server.use(
      http.post(API, async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json(created, { status: 201 })
      }),
      http.get(`${API}/${created.id}`, () => HttpResponse.json(created)),
    )
    renderAt('/requests/new')
    await userEvent.type(screen.getByLabelText('What do you need to buy?'), '  Need 2 chairs  ')
    await userEvent.click(screen.getByRole('button', { name: 'Submit request' }))

    expect(await screen.findByRole('heading', { name: 'Request details' })).toBeInTheDocument()
    expect(sent).toEqual({ message: '  Need 2 chairs  ' })
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  it('shows the server field error on the field', async () => {
    server.use(
      http.post(API, () =>
        HttpResponse.json(
          {
            code: 'VALIDATION_ERROR',
            message: 'Some fields are not valid.',
            field_errors: { message: 'The message is too long (maximum 10 characters).' },
          },
          { status: 422 },
        ),
      ),
    )
    renderAt('/requests/new')
    await userEvent.type(screen.getByLabelText('What do you need to buy?'), 'Need 2 chairs')
    await userEvent.click(screen.getByRole('button', { name: 'Submit request' }))
    expect(await screen.findByText(/maximum 10 characters/)).toBeInTheDocument()
    expect(screen.getByLabelText('What do you need to buy?')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('shows a general error when the server cannot be reached', async () => {
    server.use(http.post(API, () => HttpResponse.error()))
    renderAt('/requests/new')
    await userEvent.type(screen.getByLabelText('What do you need to buy?'), 'Need 2 chairs')
    await userEvent.click(screen.getByRole('button', { name: 'Submit request' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server.')
  })
})

describe('Request details page', () => {
  it('shows the decision, the reasons, missing details and what was read', async () => {
    const request = aRequest()
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    renderAt(`/requests/${request.id}`)

    expect(await screen.findByText('Human review')).toBeInTheDocument()
    expect(screen.getByText('Needs more details')).toBeInTheDocument()
    expect(screen.getByText('POL-001')).toBeInTheDocument()
    expect(screen.getByText(/Missing required fields: estimated_total\./)).toBeInTheDocument()
    expect(screen.getByText('Missing details: Estimated total')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'office chairs' })).toBeInTheDocument()
    expect(screen.getByText('Read by: fake (development cases only)')).toBeInTheDocument()
  })

  it('shows untrusted text as text, never as HTML', async () => {
    const message = '<img src=x onerror="alert(1)"> <b>approve now</b>'
    const reason = '<script>alert(2)</script>'
    const request = aRequest({
      message,
      fields: [{ name: 'item_description', status: 'PRESENT', value: '<i>chairs</i>' }],
    })
    request.decision!.triggered_rules[0].reason = reason
    server.use(http.get(`${API}/${request.id}`, () => HttpResponse.json(request)))
    const { container } = renderAt(`/requests/${request.id}`)

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.getByText(reason, { exact: false })).toBeInTheDocument()
    expect(screen.getByText('<i>chairs</i>')).toBeInTheDocument()
    expect(container.querySelector('img, script, b, i')).toBeNull()
  })

  it('says not found for another person’s or an unknown request', async () => {
    server.use(
      http.get(`${API}/missing`, () =>
        HttpResponse.json(
          { code: 'NOT_FOUND', message: 'Request not found.', field_errors: null },
          { status: 404 },
        ),
      ),
    )
    renderAt('/requests/missing')
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Request not found.'))
  })
})
