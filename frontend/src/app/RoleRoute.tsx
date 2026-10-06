import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useSession } from '../hooks/useSession'
import type { UserRole } from '../types/api'

/**
 * Only ever rendered inside ProtectedRoute, so a session is guaranteed to
 * exist. If the current role isn't allowed, redirect to the dashboard
 * instead of showing a dead-end "forbidden" page — the nav itself never
 * offers a link a role can't use, so reaching this case means a typed-in
 * URL, not a broken flow.
 */
export function RoleRoute({ allow, children }: { allow: UserRole[]; children: ReactNode }) {
  const { user } = useSession()
  if (!user) return null
  if (!allow.includes(user.role)) {
    return <Navigate to="/app" replace />
  }
  return <>{children}</>
}
