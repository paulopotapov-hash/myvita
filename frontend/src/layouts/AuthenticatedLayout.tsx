import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { useLogout } from '../hooks/useAuthMutations'
import { useSession } from '../hooks/useSession'
import { toUserMessage } from '../lib/errorMessages'

export interface NavItem {
  to: string
  label: string
}

interface AuthenticatedLayoutProps {
  areaLabel: string
  homePath: string
  navItems: NavItem[]
}

export function AuthenticatedLayout({ areaLabel, homePath, navItems }: AuthenticatedLayoutProps) {
  const { user } = useSession()
  const logout = useLogout()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  if (!user) return null

  const navLinkClassName = ({ isActive }: { isActive: boolean }) =>
    `block rounded-md px-3 py-2 text-sm font-medium ${
      isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-600 hover:bg-slate-100'
    }`

  const navigation = (mobile: boolean) =>
    navItems.map((item) => (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === homePath}
        className={navLinkClassName}
        onClick={mobile ? () => setMobileNavOpen(false) : undefined}
      >
        {item.label}
      </NavLink>
    ))

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white md:block">
        <div className="px-4 py-5">
          <p className="flex items-center gap-2 text-lg font-semibold tracking-tight text-teal-700">
            myVita <Logo size="header" alt="" />
          </p>
        </div>
        <nav className="flex flex-col gap-1 px-2" aria-label="Navegação principal">
          {navigation(false)}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
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
          <p className="flex items-center gap-1.5 text-base font-semibold tracking-tight text-teal-700 md:hidden">
            myVita <Logo size="header" alt="" />
          </p>

          <div className="ml-auto flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
              <p className="text-xs text-slate-500">{areaLabel}</p>
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
        {mobileNavOpen && (
          <nav className="border-b border-slate-200 bg-white px-2 py-2 md:hidden" aria-label="Navegação principal">
            {navigation(true)}
          </nav>
        )}
        <main className="flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
