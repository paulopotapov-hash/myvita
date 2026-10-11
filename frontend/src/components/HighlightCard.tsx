import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon, type IconName } from './Icon'

/** Highlight card on the patient home: a titled summary with one primary action. */
export function HighlightCard({ id, title, icon, children, actionLabel, actionTo }: {
  id: string
  title: string
  icon: IconName
  children: ReactNode
  actionLabel: string
  actionTo: string
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700" aria-hidden="true">
          <Icon name={icon} className="h-6 w-6" />
        </span>
        <h2 id={id} className="text-lg font-semibold text-slate-900">{title}</h2>
      </div>
      <div className="text-base text-slate-700">{children}</div>
      <Link
        to={actionTo}
        className="inline-flex min-h-11 items-center justify-center self-start rounded-full bg-teal-700 px-5 text-base font-medium text-white hover:bg-teal-800"
      >
        {actionLabel}
      </Link>
    </section>
  )
}
