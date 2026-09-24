import { useId } from 'react'
import { Link } from 'react-router-dom'
import type { AppointmentPublic } from '../../types/api'
import { AppointmentStatusBadge } from '../AppointmentStatusBadge'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'

interface Props {
  title: string
  appointments: AppointmentPublic[] | undefined
  isLoading: boolean
  error: unknown
  onRetry: () => void
  emptyTitle: string
  emptyDescription: string
  counterpartName?: (appointment: AppointmentPublic) => string | undefined
}

export function DashboardAppointments({
  title,
  appointments,
  isLoading,
  error,
  onRetry,
  emptyTitle,
  emptyDescription,
  counterpartName,
}: Props) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 id={headingId} className="text-lg font-semibold text-slate-900">
          {title}
        </h2>
        <Link
          to="/app/consultas"
          className="text-sm font-medium text-teal-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        >
          Ver todas
        </Link>
      </div>

      {isLoading && <AppointmentsSkeleton />}
      {error !== null && error !== undefined && <ErrorState message={toUserMessage(error)} onRetry={onRetry} />}
      {appointments && appointments.length === 0 && (
        <EmptyState
          title={emptyTitle}
          description={emptyDescription}
          action={
            <Link to="/app/consultas" className="mt-2 text-sm font-medium text-teal-700 hover:underline">
              Ir para consultas
            </Link>
          }
        />
      )}
      {appointments && appointments.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {appointments.map((appointment) => {
            const counterpart = counterpartName?.(appointment)
            return (
              <li key={appointment.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
                  <p className="mt-0.5 text-sm text-slate-500">
                    {[counterpart, `${appointment.duration_minutes} min`].filter(Boolean).join(' · ')}
                  </p>
                  {appointment.reason && <p className="mt-1 truncate text-sm text-slate-500">{appointment.reason}</p>}
                </div>
                <div className="shrink-0 self-start sm:self-auto">
                  <AppointmentStatusBadge status={appointment.status} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function AppointmentsSkeleton() {
  return (
    <div role="status" aria-label="A carregar consultas" className="space-y-4">
      {[0, 1, 2].map((item) => (
        <div key={item} className="animate-pulse border-b border-slate-100 pb-4 last:border-0">
          <div className="h-4 w-40 rounded bg-slate-200" />
          <div className="mt-2 h-3 w-28 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  )
}
