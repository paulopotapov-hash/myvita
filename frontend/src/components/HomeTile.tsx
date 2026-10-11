import { Link } from 'react-router-dom'
import { badgeText } from '../lib/navItems'
import { Icon, type IconName } from './Icon'

/** Square shortcut on the patient home: large icon, short label, unread badge. */
export function HomeTile({ to, label, icon, badge = 0, badgeLabel }: {
  to: string
  label: string
  icon: IconName
  badge?: number
  /** Screen-reader text for the badge, e.g. "2 conversas por ler". */
  badgeLabel?: string
}) {
  return (
    <Link
      to={to}
      className="relative flex aspect-square flex-col items-center justify-center gap-2 rounded-2xl bg-white px-1 py-3 text-center shadow-sm ring-1 ring-slate-100 transition-colors hover:bg-teal-50"
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-50 text-teal-700" aria-hidden="true">
        <Icon name={icon} className="h-7 w-7" />
      </span>
      <span className="text-[clamp(0.875rem,4.3vw,1rem)] font-medium leading-tight text-slate-800">{label}</span>
      {badge > 0 && (
        <span className="absolute right-2 top-2 inline-flex min-w-6 items-center justify-center rounded-full bg-teal-700 px-1.5 py-0.5 text-sm font-semibold text-white">
          <span aria-hidden="true">{badgeText(badge)}</span>
          {badgeLabel && <span className="sr-only">{`, ${badgeLabel}`}</span>}
        </span>
      )}
    </Link>
  )
}
