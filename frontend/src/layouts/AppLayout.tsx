import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useLogout } from '../hooks/useAuthMutations'
import { useSession } from '../hooks/useSession'
import type { UserRole } from '../types/api'
import { toUserMessage } from '../lib/errorMessages'

interface NavItem {
  to: string
  label: string
}

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  patient: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'As minhas consultas' },
    { to: '/app/perfil', label: 'Perfil' },
    { to: '/app/saude', label: 'Saúde' },
    { to: '/app/mensagens', label: 'Mensagens' },
    { to: '/app/notificacoes', label: 'Notificações' },
    { to: '/app/seguranca', label: 'Segurança' },
  ],
  staff: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'Consultas' },
    { to: '/app/pacientes', label: 'Pacientes' },
    { to: '/app/mensagens', label: 'Mensagens' },
    { to: '/app/notificacoes', label: 'Notificações' },
    { to: '/app/seguranca', label: 'Segurança' },
  ],
  clinic_admin: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'Consultas' },
    { to: '/app/pacientes', label: 'Pacientes' },
    { to: '/app/equipa', label: 'Equipa' },
    { to: '/app/contas', label: 'Contas' },
    { to: '/app/notificacoes', label: 'Notificações' },
    { to: '/app/seguranca', label: 'Segurança' },
  ],
}

const ROLE_LABELS: Record<UserRole, string> = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
}

export function AppLayout() {
  const { user } = useSession()
  const logout = useLogout()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()
  const mainRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const previousPath = useRef<string | null>(null)
  const role = user?.role
  const navItems = role
    ? NAV_BY_ROLE[role].filter(
        (item) => item.to !== '/app/mensagens' || user.role === 'patient' || user.staff_role === 'doctor' || user.staff_role === 'nurse',
      )
    : []

  // A client-side navigation is silent for assistive tech: name the page and move focus to it.
  useEffect(() => {
    const current = (role ? NAV_BY_ROLE[role] : [])
      .filter((item) => (item.to === '/app' ? location.pathname === '/app' : location.pathname.startsWith(item.to)))
      .sort((a, b) => b.to.length - a.to.length)[0]
    document.title = current ? `${current.label} · myVita` : 'myVita'
    if (previousPath.current !== null && previousPath.current !== location.pathname) mainRef.current?.focus()
    previousPath.current = location.pathname
  }, [location.pathname, role])

  useEffect(() => {
    if (!mobileNavOpen) return
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setMobileNavOpen(false)
      menuButtonRef.current?.focus()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [mobileNavOpen])

  if (!user) return null // ProtectedRoute guarantees this never renders without a user

  const navLinkClassName = ({ isActive }: { isActive: boolean }) =>
    `block rounded-md px-3 py-2 text-sm font-medium ${
      isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-100'
    }`

  return (
    <div className="flex min-h-screen bg-slate-50">
      <a
        href="#main-content"
        onClick={(event) => {
          event.preventDefault()
          mainRef.current?.focus()
        }}
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-teal-800 focus:shadow"
      >
        Saltar para o conteúdo
      </a>
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white md:block">
        <div className="px-4 py-5">
          <p className="text-lg font-semibold tracking-tight text-teal-700">myVita</p>
        </div>
        <nav className="flex flex-col gap-1 px-2" aria-label="Navegação principal">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/app'} className={navLinkClassName}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
          <button
            ref={menuButtonRef}
            type="button"
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-label="Menu de navegação"
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-nav"
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="ml-auto flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
              <p className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</p>
            </div>
            <button
              type="button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {logout.isPending ? 'A sair…' : 'Sair'}
            </button>
          </div>
        </header>
        {logout.isError && (
          <p role="alert" className="border-b border-red-200 bg-red-50 px-4 py-2 text-right text-sm text-red-700">
            {toUserMessage(logout.error)}
          </p>
        )}

        {/* Mobile nav drawer */}
        {mobileNavOpen && (
          <nav
            id="mobile-nav"
            className="border-b border-slate-200 bg-white px-2 py-2 md:hidden"
            aria-label="Navegação principal"
          >
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/app'}
                className={navLinkClassName}
                onClick={() => setMobileNavOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}

        <main id="main-content" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 outline-none md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
