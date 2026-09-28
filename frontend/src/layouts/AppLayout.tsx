import { useSession } from '../hooks/useSession'
import { AuthenticatedLayout, type NavItem } from './AuthenticatedLayout'

const STAFF_NAV: NavItem[] = [
  { to: '/app', label: 'Início' },
  { to: '/app/consultas', label: 'Consultas' },
  { to: '/app/pacientes', label: 'Pacientes' },
  { to: '/app/notificacoes', label: 'Notificações' },
]

const ADMIN_NAV: NavItem[] = [
  { to: '/app', label: 'Início' },
  { to: '/app/consultas', label: 'Consultas' },
  { to: '/app/pacientes', label: 'Pacientes' },
  { to: '/app/equipa', label: 'Equipa' },
  { to: '/app/notificacoes', label: 'Notificações' },
]

export function AppLayout() {
  const { user } = useSession()
  if (!user || user.role === 'patient') return null

  const isAdmin = user.role === 'clinic_admin'
  return (
    <AuthenticatedLayout
      areaLabel={isAdmin ? 'Administrador da clínica' : 'Profissional de saúde'}
      homePath="/app"
      navItems={isAdmin ? ADMIN_NAV : STAFF_NAV}
    />
  )
}
