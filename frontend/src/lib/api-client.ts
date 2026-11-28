/**
 * The ONLY place that calls fetch. Every feature's API functions use this.
 * Errors are normalized into one shape so every screen handles them the same way.
 * The backend sends every error as {code, message, field_errors} (Handbook §3, Q-002).
 */
export type ApiError = {
  code: string
  message: string
  fieldErrors?: Record<string, string>
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

const DEMO_USER_KEY = 'demoUser'

/**
 * Development user switcher (D-065): the demo user to act as, sent as X-Demo-User.
 * Not security: the backend refuses the header outside development. Storage may be
 * unavailable, so every access is guarded.
 */
export function getDemoUser(): string | null {
  try {
    return localStorage.getItem(DEMO_USER_KEY)
  } catch {
    return null
  }
}

export function setDemoUser(email: string | null): void {
  try {
    if (email) localStorage.setItem(DEMO_USER_KEY, email)
    else localStorage.removeItem(DEMO_USER_KEY)
  } catch {
    // Without storage the choice lasts until the page reloads only.
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringRecord(value: unknown): Record<string, string> | undefined {
  if (!isRecord(value)) return undefined
  const entries = Object.entries(value).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  )
  return entries.length > 0 ? Object.fromEntries(entries) : undefined
}

/** Turn any error response body into an ApiError, without trusting its shape. */
export function toApiError(status: number, body: unknown): ApiError {
  const code = isRecord(body) && typeof body.code === 'string' ? body.code : `HTTP_${status}`
  const message =
    isRecord(body) && typeof body.message === 'string' ? body.message : 'Something went wrong.'
  const fieldErrors = isRecord(body) ? stringRecord(body.field_errors) : undefined
  return fieldErrors ? { code, message, fieldErrors } : { code, message }
}

export function isApiError(value: unknown): value is ApiError {
  return isRecord(value) && typeof value.code === 'string' && typeof value.message === 'string'
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(getDemoUser() ? { 'X-Demo-User': getDemoUser() as string } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw { code: 'NETWORK_ERROR', message: 'Could not reach the server.' } satisfies ApiError
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw toApiError(response.status, body)
  }
  return (await response.json()) as T
}
