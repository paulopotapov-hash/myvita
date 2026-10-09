import { useSession } from '../hooks/useSession'
import { canUseMessaging } from '../lib/messaging'
import { AuthenticatedLayout, type NavItem } from './AuthenticatedLayout'

const STAFF_NAV: NavItem[] = [
  { to: '/app', label: 'Início' },
  { to: '/app/consultas', label: 'Consultas' },
  { to: '/app/pacientes', label: 'Pacientes' },
  { to: '/app/notificacoes', label: 'Notificações' },
  { to: '/app/mensagens', label: 'Mensagens' },
  { to: '/app/perfil', label: 'Perfil' },
  { to: '/app/seguranca', label: 'Segurança' },
]

const ADMIN_NAV: NavItem[] = [
  { to: '/app', label: 'Início' },
  { to: '/app/consultas', label: 'Consultas' },
  { to: '/app/pacientes', label: 'Pacientes' },
  { to: '/app/equipa', label: 'Equipa' },
  { to: '/app/contas', label: 'Contas' },
  { to: '/app/notificacoes', label: 'Notificações' },
  { to: '/app/perfil', label: 'Perfil' },
  { to: '/app/seguranca', label: 'Segurança' },
]

export function AppLayout() {
  const { user } = useSession()
  if (!user || user.role === 'patient') return null

  const isAdmin = user.role === 'clinic_admin'
  return (
    <AuthenticatedLayout
      areaLabel={isAdmin ? 'Administrador da clínica' : 'Profissional de saúde'}
      homePath="/app"
      // Messaging is for doctors/nurses only (the backend enforces it too).
      navItems={isAdmin ? ADMIN_NAV : STAFF_NAV.filter((item) => item.to !== '/app/mensagens' || canUseMessaging(user))}
    />
  )
}
