import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SESSION_QUERY_KEY } from '../hooks/useSession'
import {
  clearAuthenticatedState,
  hasAuthenticatedSession,
  publishAuthEvent,
  safeReturnTo,
  subscribeToAuthEvents,
} from '../lib/authSession'
import { setUnauthorizedHandler } from '../lib/apiClient'

/** Connects the framework-agnostic API client to React Router and Query.
 * It also mirrors login/logout events between tabs without sharing tokens. */
export function AuthCoordinator() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const currentLocation = `${location.pathname}${location.search}${location.hash}`

    return setUnauthorizedHandler((requestPath) => {
      // A normal unauthenticated /me probe and bad credentials on /login are
      // expected 401s. Only expire a session that the UI currently knows.
      if (requestPath.endsWith('/auth/login') || !hasAuthenticatedSession(queryClient)) return

      clearAuthenticatedState(queryClient)
      publishAuthEvent('logout')
      if (location.pathname.startsWith('/app')) {
        navigate('/login', { replace: true, state: { from: safeReturnTo(currentLocation) } })
      }
    })
  }, [location, navigate, queryClient])

  useEffect(
    () =>
      subscribeToAuthEvents((event) => {
        if (event === 'logout') {
          const currentLocation = `${location.pathname}${location.search}${location.hash}`
          clearAuthenticatedState(queryClient)
          if (location.pathname.startsWith('/app')) {
            navigate('/login', { replace: true, state: { from: safeReturnTo(currentLocation) } })
          }
          return
        }

        // Another tab logged in. The cookie is shared, but the user object is
        // not: ask the backend for the authoritative identity.
        void queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })
      }),
    [location, navigate, queryClient],
  )

  return null
}
