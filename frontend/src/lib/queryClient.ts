import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './apiClient'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 401/403/404 will never succeed on retry — only retry once for
      // transient failures (network blips, a 5xx), never hammer the
      // backend for something that requires the user to act (log in again).
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500 && error.status !== 429) return false
        return failureCount < 2
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false, // never silently retry a POST/PATCH/DELETE — could double-submit
    },
  },
})
