import { useMutation, useQueryClient } from '@tanstack/react-query'
import { authService } from '../services/auth'
import { SESSION_QUERY_KEY } from './useSession'
import { isMfaChallenge } from '../types/api'
import type { LoginRequest } from '../types/api'

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LoginRequest) => authService.login(payload),
    onSuccess: (result) => {
      // A successful login may replace an expired or different identity.
      // Never let tenant-scoped data survive that identity boundary.
      queryClient.clear()
      // A challenge is not a session yet: the second factor comes next.
      if (!isMfaChallenge(result)) queryClient.setQueryData(SESSION_QUERY_KEY, result)
    },
  })
}

export function useVerifyMfa() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => authService.verifyMfa(code),
    onSuccess: (user) => {
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
