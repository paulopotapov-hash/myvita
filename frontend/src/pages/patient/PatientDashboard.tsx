import { Link } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useAppointments } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { formatDateTime } from '../../lib/formatDate'
import { toUserMessage } from '../../lib/errorMessages'

export function PatientDashboard() {
  const { user } = useSession()
  const appointments = useAppointments()

  const upcoming = (appointments.data ?? [])
    .filter((a) => a.status === 'scheduled' || a.status === 'confirmed')
    .filter((a) => new Date(a.scheduled_at) >= new Date())
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
    .slice(0, 3)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Olá, {user?.full_name}</h1>
        <p className="text-slate-500">Bem-vindo(a) à tua área myVita.</p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium text-slate-900">Próximas consultas</h2>
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && upcoming.length === 0 && (
          <EmptyState title="Sem consultas agendadas" description="Ainda não tens consultas marcadas." />
        )}
        {upcoming.length > 0 && (
          <ul className="flex flex-col divide-y divide-slate-100">
            {upcoming.map((appointment) => (
              <li key={appointment.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
                  {appointment.reason && <p className="text-sm text-slate-500">{appointment.reason}</p>}
                </div>
                <AppointmentStatusBadge status={appointment.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex flex-wrap gap-3">
        <Link
          to="/app/consultas"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Ver todas as consultas
        </Link>
        <Link
          to="/app/perfil"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          O meu perfil
        </Link>
      </div>
    </div>
  )
}
