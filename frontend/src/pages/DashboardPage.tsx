import { AdminDashboard } from './admin/AdminDashboard'
import { PatientDashboard } from './patient/PatientDashboard'
import { StaffDashboard } from './staff/StaffDashboard'
import { useSession } from '../hooks/useSession'

export function DashboardPage() {
  const { user } = useSession()
  if (!user) return null

  switch (user.role) {
    case 'patient':
      return <PatientDashboard />
    case 'staff':
      return <StaffDashboard />
    case 'clinic_admin':
      return <AdminDashboard />
  }
}
