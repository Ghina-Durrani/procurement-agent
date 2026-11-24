import { describe, expect, it } from 'vitest'
import { isApiError, toApiError } from './api-client'

describe('toApiError', () => {
  it('reads the backend error envelope', () => {
    expect(
      toApiError(422, {
        code: 'VALIDATION_ERROR',
        message: 'Some fields are not valid.',
        field_errors: { message: 'Write what you need to buy.' },
      }),
    ).toEqual({
      code: 'VALIDATION_ERROR',
      message: 'Some fields are not valid.',
      fieldErrors: { message: 'Write what you need to buy.' },
    })
  })

  it('falls back safely when the body is not the envelope', () => {
    expect(toApiError(500, null)).toEqual({ code: 'HTTP_500', message: 'Something went wrong.' })
    expect(toApiError(404, { detail: 'x' })).toEqual({
      code: 'HTTP_404',
      message: 'Something went wrong.',
    })
  })

  it('ignores field errors that are not text', () => {
    expect(toApiError(422, { code: 'X', message: 'm', field_errors: { a: 1 } })).toEqual({
      code: 'X',
      message: 'm',
    })
  })
})

describe('isApiError', () => {
  it('recognises the normalized shape only', () => {
    expect(isApiError({ code: 'A', message: 'b' })).toBe(true)
    expect(isApiError(new Error('x'))).toBe(false)
  })
})
