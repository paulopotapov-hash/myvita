import { Navigate } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { SplashGate } from '../components/SplashGate'
import { useSession } from '../hooks/useSession'
import { homePathForRole } from '../lib/navigation'

export function RootRedirect() {
  const { isLoading, user } = useSession()
  if (isLoading) return <LoadingSpinner />
  return (
    <SplashGate>
      <Navigate to={user ? homePathForRole(user.role) : '/login'} replace />
    </SplashGate>
  )
}
