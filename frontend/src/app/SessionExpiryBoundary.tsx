import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SESSION_EXPIRED_EVENT } from '../lib/apiClient'

/** Converts an operational API 401 into the same deterministic signed-out
 * state as an initial /auth/me 401. Cookies remain server-owned. */
export function SessionExpiryBoundary() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    function onExpired(event: Event) {
      const apiPath = (event as CustomEvent<{ path?: string }>).detail?.path
      if (apiPath === '/api/v1/auth/login') return
      queryClient.clear()
      if (location.pathname !== '/login') {
        navigate('/login', {
          replace: true,
          state: { from: `${location.pathname}${location.search}` },
        })
      }
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [location.pathname, location.search, navigate, queryClient])

  return null
}
