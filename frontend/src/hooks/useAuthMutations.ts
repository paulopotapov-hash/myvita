import { useMutation, useQueryClient } from '@tanstack/react-query'
import { authService } from '../services/auth'
import { SESSION_QUERY_KEY } from './useSession'
import type { LoginRequest } from '../types/api'

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LoginRequest) => authService.login(payload),
    onSuccess: (user) => {
      // A successful login may replace an expired or different identity.
      // Never let tenant-scoped data survive that identity boundary.
      queryClient.clear()
      queryClient.setQueryData(SESSION_QUERY_KEY, user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => authService.logout(),
    onSuccess: () => {
      queryClient.setQueryData(SESSION_QUERY_KEY, null)
      // Every other cached query may contain data scoped to the session
      // that just ended (another clinic's patients after the next login,
      // for instance) — clear everything, not just the session itself.
      queryClient.clear()
    },
  })
}
