import { AuthenticatedLayout, type NavItem } from './AuthenticatedLayout'

const PATIENT_NAV: NavItem[] = [
  { to: '/patient', label: 'Início' },
  { to: '/patient/consultas', label: 'Consultas' },
  { to: '/patient/saude', label: 'Dados clínicos' },
  { to: '/patient/perfil', label: 'Perfil' },
  { to: '/patient/notificacoes', label: 'Notificações' },
]

export function PatientLayout() {
  return <AuthenticatedLayout areaLabel="Área do paciente" homePath="/patient" navItems={PATIENT_NAV} />
}
