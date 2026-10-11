import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { NavLink } from 'react-router-dom'
import { badgeText, type NavBadge, type NavItem } from '../lib/navItems'
import { Icon } from './Icon'
import { Logo } from './Logo'

export type BadgeCounts = Record<NavBadge, number>

const BADGE_SR: Record<NavBadge, (count: number) => string> = {
  messages: (count) => (count === 1 ? '1 conversa por ler' : `${count} conversas por ler`),
  notifications: (count) => (count === 1 ? '1 notificação por ler' : `${count} notificações por ler`),
}

/** The account's sections, with icons and unread badges. Shared by the desktop sidebar and the mobile drawer. */
export function NavList({ items, homePath, badges, onNavigate }: {
  items: NavItem[]
  homePath: string
  badges: BadgeCounts
  onNavigate?: () => void
}) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item) => {
        const count = item.badge ? badges[item.badge] : 0
        return (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === homePath}
              onClick={onNavigate}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-base font-medium ${
                  isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-700 hover:bg-slate-100'
                }`
              }
            >
              <Icon name={item.icon} className="h-6 w-6 shrink-0" />
              <span className="flex-1">{item.label}</span>
              {item.badge && count > 0 && (
                <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-teal-700 px-2 py-0.5 text-sm font-semibold text-white">
                  <span aria-hidden="true">{badgeText(count)}</span>
                  <span className="sr-only">{`, ${BADGE_SR[item.badge](count)}`}</span>
                </span>
              )}
            </NavLink>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * Mobile navigation drawer (modal): opens from the left, closes on Escape, on a
 * tap outside, on the close button or when a section is chosen. Focus stays
 * inside while open; the caller returns it to the menu button on close.
 */
export function NavDrawer({ id, open, onClose, items, homePath, badges }: {
  id: string
  open: boolean
  onClose: () => void
  items: NavItem[]
  homePath: string
  badges: BadgeCounts
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key === 'Tab') trapFocus(event, panelRef)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      {/* Tapping outside the panel closes it; keyboard users have Escape and the close button. */}
      <div className="absolute inset-0 bg-slate-900/40" aria-hidden="true" onClick={onClose} />
      <div
        id={id}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-xl"
      >
        <div className="flex h-16 items-center justify-between px-4">
          <span className="flex items-center gap-1.5 text-lg font-semibold tracking-tight text-teal-700">
            myVita <Logo size="header" alt="" />
          </span>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Fechar menu"
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100"
          >
            <Icon name="close" />
          </button>
        </div>
        <nav aria-label="Navegação principal" className="flex-1 overflow-y-auto px-3 pb-6">
          <NavList items={items} homePath={homePath} badges={badges} onNavigate={onClose} />
        </nav>
      </div>
    </div>
  )
}

function trapFocus(event: KeyboardEvent, container: RefObject<HTMLElement | null>) {
  const focusable = container.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
  if (!focusable || focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
