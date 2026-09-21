import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useLogout } from '../hooks/useAuthMutations'
import { useSession } from '../hooks/useSession'
import type { UserRole } from '../types/api'

interface NavItem {
  to: string
  label: string
}

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  patient: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'As minhas consultas' },
    { to: '/app/perfil', label: 'Perfil' },
  ],
  staff: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'Consultas' },
    { to: '/app/pacientes', label: 'Pacientes' },
  ],
  clinic_admin: [
    { to: '/app', label: 'Início' },
    { to: '/app/consultas', label: 'Consultas' },
    { to: '/app/pacientes', label: 'Pacientes' },
    { to: '/app/equipa', label: 'Equipa' },
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

  if (!user) return null // ProtectedRoute guarantees this never renders without a user
  const navItems = NAV_BY_ROLE[user.role]

  const navLinkClassName = ({ isActive }: { isActive: boolean }) =>
    `block rounded-md px-3 py-2 text-sm font-medium ${
      isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-100'
    }`

  return (
    <div className="flex min-h-screen bg-slate-50">
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
            type="button"
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-label="Abrir menu de navegação"
            aria-expanded={mobileNavOpen}
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

        {/* Mobile nav drawer */}
        {mobileNavOpen && (
          <nav
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

        <main className="flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
