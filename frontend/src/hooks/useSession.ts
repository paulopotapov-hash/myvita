import { useQuery } from '@tanstack/react-query'
import { authService } from '../services/auth'
import { ApiError } from '../lib/apiClient'

export const SESSION_QUERY_KEY = ['session'] as const

/**
 * Wraps GET /api/v1/auth/me. Distinguishes exactly the four states the
 * rest of the app needs — see backend/README.md's auth section for why
 * 401 here means "not logged in" (expected, not an error) while a network
 * failure or 5xx is a genuine error state that shouldn't be confused with
 * "please log in".
 */
export function useSession() {
  const query = useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: ({ signal }) => authService.me(signal),
    retry: false, // a 401 will never succeed on retry — don't hammer the backend
    staleTime: 60_000,
  })

  const isUnauthenticated = query.isError && query.error instanceof ApiError && query.error.status === 401
  const isServerError = query.isError && !isUnauthenticated

  return {
    user: query.data ?? null,
    isLoading: query.isLoading,
    isAuthenticated: query.isSuccess,
    isUnauthenticated,
    isServerError,
    refetch: query.refetch,
  }
}
