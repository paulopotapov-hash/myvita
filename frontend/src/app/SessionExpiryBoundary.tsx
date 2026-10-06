import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SESSION_QUERY_KEY } from '../hooks/useSession'
import { ACCOUNT_ACTION_REQUIRED_EVENT, SESSION_EXPIRED_EVENT } from '../lib/apiClient'

/** Converts an operational API 401 into the same deterministic signed-out
 * state as an initial /auth/me 401. Cookies remain server-owned. */
export function SessionExpiryBoundary() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    function onExpired(event: Event) {
      if (!(event instanceof CustomEvent)) return
      const detail: unknown = event.detail
      const apiPath =
        typeof detail === 'object' && detail !== null && 'path' in detail && typeof detail.path === 'string'
          ? detail.path
          : undefined
      // Wrong credentials or a wrong/expired second-factor code are form
      // errors, not an expired session (the enrolment form runs inside /app).
      if (apiPath === '/api/v1/auth/login' || apiPath?.startsWith('/api/v1/auth/mfa/')) return
      queryClient.clear()
      if (location.pathname !== '/login') {
        navigate('/login', {
          replace: true,
          state: { from: `${location.pathname}${location.search}` },
        })
      }
    }
    // An account obligation appeared mid-session (e.g. an admin required a
    // password change): refetch /auth/me so ProtectedRoute shows the
    // account-setup gate instead of a page full of 403 errors.
    function onAccountAction() {
      void queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    window.addEventListener(ACCOUNT_ACTION_REQUIRED_EVENT, onAccountAction)
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
      window.removeEventListener(ACCOUNT_ACTION_REQUIRED_EVENT, onAccountAction)
    }
  }, [location.pathname, location.search, navigate, queryClient])

  return null
}
