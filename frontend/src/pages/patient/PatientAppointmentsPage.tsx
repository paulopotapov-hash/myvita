import { useState } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { AppointmentRequestsPanel } from '../../components/AppointmentRequestsPanel'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { Icon } from '../../components/Icon'
import { WaitlistOffersPanel } from '../../components/scheduling/WaitlistOffersPanel'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useAppointments } from '../../hooks/useClinicData'
import { formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { isUpcoming } from '../../lib/appointments'
import { toUserMessage } from '../../lib/errorMessages'
import type { AppointmentPatientView } from '../../types/api'

type Tab = 'upcoming' | 'past'

/** "As minhas consultas": upcoming and past appointments, booking, and pending requests. */
export function PatientAppointmentsPage() {
  const [params] = useSearchParams()
  const requested = (useLocation().state as { requested?: boolean } | null)?.requested === true
  const appointments = useAppointments()
  const [tab, setTab] = useState<Tab>('upcoming')
  const [showCancelled, setShowCancelled] = useState(false)

  // Old links ("?consulta=<id>") open the appointment's own page.
  const legacy = params.get('consulta')
  if (legacy) return <Navigate to={`/patient/consultas/${encodeURIComponent(legacy)}`} replace />

  const now = new Date()
  const own = (appointments.data ?? []).filter((item): item is AppointmentPatientView => item.view === 'patient')
  const visible = own.filter((item) => showCancelled || item.status !== 'cancelled')
  const upcoming = visible.filter((item) => isUpcoming(item, now) || (item.status === 'cancelled' && new Date(item.scheduled_at) > now))
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
  const past = visible.filter((item) => !upcoming.includes(item)).sort((a, b) => b.scheduled_at.localeCompare(a.scheduled_at))
  const shown = tab === 'upcoming' ? upcoming : past
  const cancelledCount = own.filter((item) => item.status === 'cancelled').length

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">As minhas consultas</h1>
        <Link
          to="/patient/consultas/marcar"
          className="inline-flex min-h-11 items-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-base font-semibold text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        >
          <Icon name="calendarPlus" className="h-5 w-5" />
          Marcar consulta
        </Link>
      </div>

      {requested && <FormMessage kind="success">Pedido enviado. A clínica responde na app: confirma ou propõe um horário.</FormMessage>}

      <WaitlistOffersPanel />

      <div role="tablist" aria-label="Consultas" className="flex gap-2 border-b border-slate-200">
        {([['upcoming', `Próximas (${upcoming.length})`], ['past', 'Passadas']] as Array<[Tab, string]>).map(([key, label]) => (
          <button
            key={key}
            id={`appointments-tab-${key}`}
            type="button"
            role="tab"
            aria-selected={tab === key}
            aria-controls="appointments-panel"
            onClick={() => setTab(key)}
            className={`-mb-px min-h-11 border-b-2 px-4 py-2 text-sm font-medium ${tab === key ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
          >
            {label}
          </button>
        ))}
      </div>

      <section id="appointments-panel" role="tabpanel" aria-labelledby={`appointments-tab-${tab}`} className="flex flex-col gap-3">
        {appointments.isLoading && <LoadingSpinner label="A carregar as consultas…" />}
        {appointments.isError && <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />}
        {appointments.data && shown.length === 0 && (
          <EmptyState title={tab === 'upcoming' ? 'Sem consultas marcadas' : 'Sem consultas passadas'} />
        )}
        {shown.length > 0 && (
          <ul className="flex flex-col gap-3">
            {shown.map((appointment) => (
              <li key={appointment.id}>
                <Link
                  to={`/patient/consultas/${appointment.id}`}
                  className="flex flex-col gap-1 rounded-xl border border-slate-200 bg-white p-4 hover:border-teal-300 focus-visible:outline-2 focus-visible:outline-teal-700"
                >
                  <span className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-slate-900 first-letter:uppercase">{formatClinicDay(appointment.scheduled_at)}, {formatClinicTime(appointment.scheduled_at)}</span>
                    <AppointmentStatusBadge status={appointment.status} />
                  </span>
                  <span className="text-sm text-slate-600">{appointment.appointment_type} · {appointment.staff_name}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {cancelledCount > 0 && (
          <label className="flex min-h-11 items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={showCancelled} onChange={(event) => setShowCancelled(event.target.checked)} />
            Mostrar consultas canceladas ({cancelledCount})
          </label>
        )}
      </section>

      <AppointmentRequestsPanel />
    </div>
  )
}
