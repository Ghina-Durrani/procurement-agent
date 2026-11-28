import { apiRequest } from '@/lib/api-client'
import type { components } from '@/types/api.generated'

export type CurrentUser = components['schemas']['CurrentUserRead']
export type DemoUsers = components['schemas']['DemoUsers']

export function getMe(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>('/api/v1/me')
}

export function getDemoUsers(): Promise<DemoUsers> {
  return apiRequest<DemoUsers>('/api/v1/dev/users')
}
