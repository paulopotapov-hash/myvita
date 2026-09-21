import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { ErrorState } from '../components/ErrorState'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useSession } from '../hooks/useSession'

/**
 * Frontend route protection is UX protection, not authorization — the
 * backend is the actual source of truth for what a user can do (every
 * page here can call an endpoint the backend will still 401/403 on its
 * own). This only avoids showing an authenticated shell to someone with
 * no session, and avoids the classic redirect loop by treating "still
 * checking" as its own state instead of guessing.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isLoading, isAuthenticated, isUnauthenticated, isServerError, refetch } = useSession()

  if (isLoading) {
    return <LoadingSpinner label="A verificar sessão…" />
  }

  if (isServerError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <ErrorState
          message="Não foi possível confirmar a tua sessão. Tenta novamente."
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  if (isUnauthenticated) {
    return <Navigate to="/login" replace />
  }

  if (isAuthenticated) {
    return <>{children}</>
  }

  return null
}
