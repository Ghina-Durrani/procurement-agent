import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from '@/lib/api-client'
import {
  getRequest,
  listRequests,
  submitRequest,
  type RequestDetail,
  type RequestList,
} from './api'

export const requestKeys = {
  all: ['requests'] as const,
  one: (id: string) => ['requests', id] as const,
}

export function useMyRequests() {
  return useQuery<RequestList, ApiError>({ queryKey: requestKeys.all, queryFn: listRequests })
}

export function useRequest(id: string) {
  return useQuery<RequestDetail, ApiError>({
    queryKey: requestKeys.one(id),
    queryFn: () => getRequest(id),
  })
}

export function useSubmitRequest() {
  const queryClient = useQueryClient()
  return useMutation<RequestDetail, ApiError, string>({
    mutationFn: submitRequest,
    onSuccess: (created) => {
      queryClient.setQueryData(requestKeys.one(created.id), created)
      void queryClient.invalidateQueries({ queryKey: requestKeys.all, exact: true })
    },
  })
}
