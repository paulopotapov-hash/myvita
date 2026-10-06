import { Navigate } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useSession } from '../hooks/useSession'

export function RootRedirect() {
  const { isLoading, isAuthenticated } = useSession()
  if (isLoading) return <LoadingSpinner />
  return <Navigate to={isAuthenticated ? '/app' : '/login'} replace />
}
