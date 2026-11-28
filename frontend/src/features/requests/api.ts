import { apiRequest } from '@/lib/api-client'
import type { components } from '@/types/api.generated'

export type RequestDetail = components['schemas']['RequestDetail']
export type RequestSummary = components['schemas']['RequestSummary']
export type RequestList = components['schemas']['RequestList']
export type RequestStatus = components['schemas']['RequestStatus']
export type Priority = components['schemas']['Priority']
export type ClarificationRound = components['schemas']['ClarificationRead']

const PATH = '/api/v1/requests'

export function submitRequest(message: string): Promise<RequestDetail> {
  return apiRequest<RequestDetail>(PATH, { method: 'POST', body: JSON.stringify({ message }) })
}

export function listRequests(): Promise<RequestList> {
  return apiRequest<RequestList>(`${PATH}?limit=50`)
}

export function getRequest(id: string): Promise<RequestDetail> {
  return apiRequest<RequestDetail>(`${PATH}/${encodeURIComponent(id)}`)
}

export function answerClarification(id: string, answer: string): Promise<RequestDetail> {
  return apiRequest<RequestDetail>(`${PATH}/${encodeURIComponent(id)}/clarifications`, {
    method: 'POST',
    body: JSON.stringify({ answer }),
  })
}
