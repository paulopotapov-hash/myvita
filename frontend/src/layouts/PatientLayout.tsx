import { AuthenticatedLayout, type NavItem } from './AuthenticatedLayout'

const PATIENT_NAV: NavItem[] = [
  { to: '/patient', label: 'Início' },
  { to: '/patient/consultas', label: 'Consultas' },
  { to: '/patient/perfil', label: 'Perfil' },
  { to: '/patient/saude', label: 'Dados clínicos' },
  { to: '/patient/consentimentos', label: 'Consentimentos' },
  { to: '/patient/notificacoes', label: 'Notificações' },
  { to: '/patient/mensagens', label: 'Mensagens' },
  { to: '/patient/seguranca', label: 'Segurança' },
]

export function PatientLayout() {
  return <AuthenticatedLayout areaLabel="Área do paciente" homePath="/patient" navItems={PATIENT_NAV} />
}
