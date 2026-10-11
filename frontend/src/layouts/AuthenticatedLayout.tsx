import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Logo } from '../components/Logo'
import { NavDrawer, NavList, type BadgeCounts } from '../components/NavDrawer'
import { UserMenu } from '../components/UserMenu'
import { useLogout } from '../hooks/useAuthMutations'
import { useUnreadNotificationCount } from '../hooks/useClinicalData'
import { useUnreadConversationsCount } from '../hooks/useMessages'
import { useSession } from '../hooks/useSession'
import { toUserMessage } from '../lib/errorMessages'
import type { Navigation } from '../lib/navItems'

const DRAWER_ID = 'mobile-nav'
const DESKTOP_QUERY = '(min-width: 1024px)'

/**
 * Shell for every signed-in area. Mobile first: a fixed header with the menu
 * button (☰), the myVita logo and the account avatar; sections open in a drawer.
 * From 1024px the same sections are a permanent sidebar and the ☰ disappears.
 */
export function AuthenticatedLayout({ navigation }: { navigation: Navigation }) {
  const { user } = useSession()
  const logout = useLogout()
  const unreadNotifications = useUnreadNotificationCount()
  const hasMessages = navigation.items.some((item) => item.badge === 'messages')
  const unreadConversations = useUnreadConversationsCount(hasMessages)
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const mainRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const previousPath = useRef<string | null>(null)
  const { items, homePath, account, areaLabel } = navigation

  // Screen readers get the page name in the title; keyboard users land on the
  // new page's content after an in-app navigation instead of back at the top.
  useEffect(() => {
    const titled = [...items, { to: account.profile, label: 'Perfil' }, { to: account.security, label: 'Segurança' }]
    const current = titled
      .filter((item) => (item.to === homePath ? location.pathname === homePath : location.pathname.startsWith(item.to)))
      .sort((a, b) => b.to.length - a.to.length)[0]
    document.title = current ? `${current.label} · myVita` : 'myVita'
    if (previousPath.current !== null && previousPath.current !== location.pathname) mainRef.current?.focus()
    previousPath.current = location.pathname
  }, [location.pathname, items, homePath, account])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    menuButtonRef.current?.focus()
  }, [])

  // The drawer is a mobile control: close it if the window grows into the sidebar layout.
  useEffect(() => {
    if (!drawerOpen || typeof window.matchMedia !== 'function') return
    const desktop = window.matchMedia(DESKTOP_QUERY)
    const onChange = () => desktop.matches && setDrawerOpen(false)
    desktop.addEventListener?.('change', onChange)
    return () => desktop.removeEventListener?.('change', onChange)
  }, [drawerOpen])

  if (!user) return null

  const badges: BadgeCounts = {
    notifications: unreadNotifications.data?.count ?? 0,
    messages: unreadConversations,
  }
  const anyBadge = items.some((item) => item.badge && badges[item.badge] > 0)
  const logoutLabel = logout.isPending ? 'A sair…' : logout.isError ? 'Tentar sair novamente' : 'Sair'

  return (
    <div className="min-h-screen bg-slate-50">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-base focus:font-medium focus:text-teal-800 focus:shadow"
        onClick={(event) => {
          event.preventDefault()
          mainRef.current?.focus()
        }}
      >
        Saltar para o conteúdo
      </a>

      <header className="sticky top-0 z-30 flex h-16 items-center gap-1 border-b border-slate-100 bg-white px-2 sm:px-4 lg:px-6">
        <button
          ref={menuButtonRef}
          type="button"
          className="relative inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100 lg:hidden"
          aria-label="Menu de navegação"
          aria-describedby={anyBadge ? 'menu-news' : undefined}
          aria-expanded={drawerOpen}
          aria-controls={DRAWER_ID}
          onClick={() => setDrawerOpen((open) => !open)}
        >
          <Icon name="menu" />
          {anyBadge && (
            <>
              <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-teal-600 ring-2 ring-white" aria-hidden="true" />
              <span id="menu-news" className="sr-only">Tem itens por ler</span>
            </>
          )}
        </button>
        <Link
          to={homePath}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-lg font-semibold tracking-tight text-teal-700"
        >
          myVita <Logo size="header" alt="" />
          <span className="sr-only">, página inicial</span>
        </Link>
        <div className="ml-auto">
          <UserMenu
            name={user.full_name}
            areaLabel={areaLabel}
            account={account}
            onLogout={() => logout.mutate()}
            logoutLabel={logoutLabel}
            logoutPending={logout.isPending}
          />
        </div>
      </header>

      {logout.isError && (
        <div role="alert" className="border-b border-red-200 bg-red-50 px-4 py-3 text-base text-red-800">
          <p>{toUserMessage(logout.error)}</p>
          <p className="mt-1 text-sm">A sessão continua ativa neste ecrã. Pode voltar a tentar no menu da conta, em “{logoutLabel}”.</p>
        </div>
      )}

      <div className="lg:flex">
        <aside className="hidden w-64 shrink-0 border-r border-slate-100 bg-white lg:block">
          <nav aria-label="Navegação principal" className="sticky top-16 max-h-[calc(100vh-4rem)] overflow-y-auto px-3 py-4">
            <NavList items={items} homePath={homePath} badges={badges} />
          </nav>
        </aside>
        <main id="main-content" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 outline-none md:px-8">
          <Outlet />
        </main>
      </div>

      <NavDrawer id={DRAWER_ID} open={drawerOpen} onClose={closeDrawer} items={items} homePath={homePath} badges={badges} />
    </div>
  )
}
