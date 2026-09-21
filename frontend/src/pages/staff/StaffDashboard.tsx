import { Link } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useAppointments, usePatients } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { formatDateTime } from '../../lib/formatDate'
import { toUserMessage } from '../../lib/errorMessages'

function isToday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  return d.toDateString() === now.toDateString()
}

export function StaffDashboard() {
  const { user } = useSession()
  const appointments = useAppointments()
  const patients = usePatients()

  const today = (appointments.data ?? [])
    .filter((a) => isToday(a.scheduled_at))
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Olá, {user?.full_name}</h1>
        <p className="text-slate-500">
          {patients.data ? `${patients.data.length} paciente(s) nesta clínica.` : 'Resumo do dia.'}
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium text-slate-900">Consultas de hoje</h2>
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && today.length === 0 && (
          <EmptyState title="Sem consultas hoje" description="Não há consultas agendadas para hoje." />
        )}
        {today.length > 0 && (
          <ul className="flex flex-col divide-y divide-slate-100">
            {today.map((appointment) => (
              <li key={appointment.id} className="flex items-center justify-between py-3">
                <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
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
          to="/app/pacientes"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Ver pacientes
        </Link>
      </div>
    </div>
  )
}
