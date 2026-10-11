import type { IconName } from '../components/Icon'
import type { UserPublic } from '../types/api'
import { canUseMessaging } from './messaging'

export type NavBadge = 'notifications' | 'messages'

export interface NavItem {
  to: string
  label: string
  icon: IconName
  badge?: NavBadge
}

export interface AccountLinks {
  profile: string
  security: string
}

export interface Navigation {
  areaLabel: string
  homePath: string
  items: NavItem[]
  account: AccountLinks
}

/**
 * Drawer sections per account type. Mirrors the route guards in App.tsx and the
 * existing permission helpers; it only decides what to show (the backend and
 * RoleRoute still enforce access). Profile and security live in the avatar menu.
 */
export function navigationFor(user: Pick<UserPublic, 'role' | 'staff_role'>): Navigation {
  if (user.role === 'patient') {
    return {
      areaLabel: 'Área do paciente',
      homePath: '/patient',
      account: { profile: '/patient/perfil', security: '/patient/seguranca' },
      items: [
        { to: '/patient', label: 'Início', icon: 'home' },
        { to: '/patient/consultas', label: 'Consultas', icon: 'calendar' },
        { to: '/patient/mensagens', label: 'Mensagens', icon: 'chat', badge: 'messages' },
        { to: '/patient/resultados', label: 'Resultados', icon: 'results' },
        { to: '/patient/documentos', label: 'Documentos', icon: 'document' },
        { to: '/patient/saude', label: 'Dados clínicos', icon: 'clipboard' },
        { to: '/patient/consentimentos', label: 'Consentimentos', icon: 'check' },
        { to: '/patient/notificacoes', label: 'Notificações', icon: 'bell', badge: 'notifications' },
      ],
    }
  }
  const account = { profile: '/app/perfil', security: '/app/seguranca' }
  if (user.role === 'clinic_admin') {
    return {
      areaLabel: 'Administrador da clínica',
      homePath: '/app',
      account,
      items: [
        { to: '/app', label: 'Início', icon: 'home' },
        { to: '/app/consultas', label: 'Consultas', icon: 'calendar' },
        { to: '/app/pacientes', label: 'Pacientes', icon: 'users' },
        { to: '/app/equipa', label: 'Equipa', icon: 'team' },
        { to: '/app/contas', label: 'Contas', icon: 'key' },
        { to: '/app/notificacoes', label: 'Notificações', icon: 'bell', badge: 'notifications' },
      ],
    }
  }
  const items: NavItem[] = [
    { to: '/app', label: 'Início', icon: 'home' },
    { to: '/app/consultas', label: 'Consultas', icon: 'calendar' },
    { to: '/app/pacientes', label: 'Pacientes', icon: 'users' },
    { to: '/app/mensagens', label: 'Mensagens', icon: 'chat', badge: 'messages' },
    { to: '/app/notificacoes', label: 'Notificações', icon: 'bell', badge: 'notifications' },
  ]
  return {
    areaLabel: 'Profissional de saúde',
    homePath: '/app',
    account,
    // Messaging is for doctors/nurses only (the backend enforces it too).
    items: items.filter((item) => item.badge !== 'messages' || canUseMessaging(user)),
  }
}

/** Badge text: counts above 99 are capped so the badge stays small. */
export function badgeText(count: number): string {
  return count > 99 ? '99+' : String(count)
}
