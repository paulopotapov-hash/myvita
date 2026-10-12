import { Link, useLocation, useParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useAppointment } from '../../hooks/useClinicData'
import { formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'

/** One appointment of the patient: when, with whom, where, its state. */
export function PatientAppointmentDetailPage() {
  const { appointmentId = '' } = useParams()
  const location = useLocation()
  const appointment = useAppointment(appointmentId)
  const booked = (location.state as { booked?: boolean } | null)?.booked === true
  const data = appointment.data?.view === 'patient' ? appointment.data : null

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <nav aria-label="Breadcrumb" className="text-sm"><Link to="/patient/consultas" className="text-teal-700 underline">As minhas consultas</Link></nav>
      <h1 className="text-2xl font-semibold text-slate-900">{data ? data.appointment_type : 'Consulta'}</h1>
      {booked && <FormMessage kind="success">Consulta marcada e confirmada.</FormMessage>}
      {appointment.isLoading && <LoadingSpinner label="A carregar a consulta…" />}
      {appointment.isError && <ErrorState message={toUserMessage(appointment.error)} onRetry={() => appointment.refetch()} />}
      {data && (
        <section aria-label="Detalhes da consulta" className="rounded-xl border border-slate-200 bg-white p-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
            <dt className="text-slate-500">Data</dt><dd className="font-medium first-letter:uppercase">{formatClinicDay(data.scheduled_at)}</dd>
            <dt className="text-slate-500">Hora</dt><dd className="font-medium">{formatClinicTime(data.scheduled_at)}–{formatClinicTime(data.ends_at)}</dd>
            <dt className="text-slate-500">Profissional</dt><dd className="font-medium">{data.staff_name}</dd>
            {data.specialty && (<><dt className="text-slate-500">Especialidade</dt><dd className="font-medium">{data.specialty}</dd></>)}
            <dt className="text-slate-500">Local</dt><dd className="font-medium">{data.location ?? 'Na clínica'}</dd>
            <dt className="text-slate-500">Estado</dt><dd><AppointmentStatusBadge status={data.status} /></dd>
            {data.reason && (<><dt className="text-slate-500">Motivo</dt><dd className="whitespace-pre-wrap">{data.reason}</dd></>)}
          </dl>
        </section>
      )}
    </div>
  )
}
