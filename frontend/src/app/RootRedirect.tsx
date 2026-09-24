import { Navigate } from 'react-router-dom'
import { ErrorState } from '../components/ErrorState'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useSession } from '../hooks/useSession'

export function RootRedirect() {
  const { isLoading, isAuthenticated, isServerError, refetch } = useSession()
  if (isLoading) return <LoadingSpinner />
  if (isServerError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <ErrorState message="Não foi possível confirmar a tua sessão. Tenta novamente." onRetry={() => refetch()} />
      </div>
    )
  }
  return <Navigate to={isAuthenticated ? '/app' : '/login'} replace />
}
