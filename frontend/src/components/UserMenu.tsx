import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AccountLinks } from '../lib/navItems'
import { Avatar } from './Avatar'
import { Icon } from './Icon'

/**
 * Avatar button with the account menu: Perfil, Segurança, Sair. A disclosure
 * (not an ARIA menu): plain links and a button, reachable with Tab, closed with
 * Escape, a tap outside, or after choosing an entry.
 */
export function UserMenu({ name, areaLabel, account, onLogout, logoutLabel, logoutPending }: {
  name: string
  areaLabel: string
  account: AccountLinks
  onLogout: () => void
  logoutLabel: string
  logoutPending: boolean
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const itemClass = 'flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-left text-base text-slate-700 hover:bg-slate-100 disabled:opacity-60'
  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Menu da conta"
        aria-expanded={open}
        aria-controls="account-menu"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-11 items-center gap-2 rounded-full pr-1 pl-1 hover:bg-slate-100 lg:pr-3"
      >
        <Avatar name={name} />
        <span className="hidden text-sm font-medium text-slate-800 lg:inline">{name}</span>
      </button>
      {open && (
        <div id="account-menu" className="absolute right-0 z-40 mt-2 w-64 rounded-xl border border-slate-100 bg-white p-2 shadow-lg">
          <div className="flex items-center gap-3 px-3 py-2">
            <Avatar name={name} size="sm" />
            <div className="min-w-0">
              <p className="truncate text-base font-medium text-slate-900">{name}</p>
              <p className="text-sm text-slate-600">{areaLabel}</p>
            </div>
          </div>
          <ul className="mt-1 flex flex-col gap-1 border-t border-slate-100 pt-2">
            <li>
              <Link to={account.profile} className={itemClass} onClick={() => setOpen(false)}>
                <Icon name="user" className="h-5 w-5" /> Perfil
              </Link>
            </li>
            <li>
              <Link to={account.security} className={itemClass} onClick={() => setOpen(false)}>
                <Icon name="shield" className="h-5 w-5" /> Segurança
              </Link>
            </li>
            <li>
              <button type="button" className={itemClass} disabled={logoutPending} onClick={onLogout}>
                <Icon name="logout" className="h-5 w-5" /> {logoutLabel}
              </button>
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}
