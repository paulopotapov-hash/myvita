import { useSession } from '../hooks/useSession'
import { navigationFor } from '../lib/navItems'
import { AuthenticatedLayout } from './AuthenticatedLayout'

export function PatientLayout() {
  const { user } = useSession()
  if (!user || user.role !== 'patient') return null
  return <AuthenticatedLayout navigation={navigationFor(user)} />
}
