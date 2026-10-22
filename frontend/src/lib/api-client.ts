/**
 * The ONLY place that calls fetch. Every feature's API functions use this.
 * Errors are normalized into one shape so every screen handles them the same way.
 */
export type ApiError = {
  code: string
  message: string
  fieldErrors?: Record<string, string>
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw { code: 'NETWORK_ERROR', message: 'Could not reach the server.' } satisfies ApiError
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const message =
      typeof body === 'object' &&
      body !== null &&
      'message' in body &&
      typeof body.message === 'string'
        ? body.message
        : 'Something went wrong.'
    throw { code: `HTTP_${response.status}`, message } satisfies ApiError
  }
  return (await response.json()) as T
}
