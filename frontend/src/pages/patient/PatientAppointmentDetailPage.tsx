import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useAppointment } from '../../hooks/useClinicData'
import { useBookingSettings, useCancelBooking } from '../../hooks/useScheduling'
import { formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'

type Notice = { booked?: boolean; rescheduled?: boolean; rescheduleRequested?: boolean }

const NOTICES: Array<[keyof Notice, string]> = [
  ['booked', 'Consulta marcada e confirmada.'],
  ['rescheduled', 'Consulta remarcada. A anterior foi cancelada.'],
  ['rescheduleRequested', 'Pedido de remarcação enviado. A clínica responde na app; até lá, a consulta mantém-se.'],
]

/** One appointment of the patient: when, with whom, where, its state, and what they may
 * still do in the app (cancel or reschedule until the clinic's deadline; after it, call). */
export function PatientAppointmentDetailPage() {
  const { appointmentId = '' } = useParams()
  const location = useLocation()
  const appointment = useAppointment(appointmentId)
  const settings = useBookingSettings()
  const cancel = useCancelBooking()
  const [confirming, setConfirming] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [error, setError] = useState('')
  const notice = (location.state as Notice | null) ?? {}
  const data = appointment.data?.view === 'patient' ? appointment.data : null
  const active = data !== null && (data.status === 'scheduled' || data.status === 'confirmed')
  const phone = settings.data?.clinic_phone

  function confirmCancel() {
    setError('')
    cancel.mutate(appointmentId, {
      onSuccess: () => {
        setConfirming(false)
        setCancelled(true)
      },
      onError: (failure) => {
        setConfirming(false)
        setError(toUserMessage(failure))
      },
    })
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <nav aria-label="Breadcrumb" className="text-sm"><Link to="/patient/consultas" className="text-teal-700 underline">As minhas consultas</Link></nav>
      <h1 className="text-2xl font-semibold text-slate-900">{data ? data.appointment_type : 'Consulta'}</h1>
      {NOTICES.filter(([key]) => notice[key]).map(([key, text]) => <FormMessage key={key} kind="success">{text}</FormMessage>)}
      {cancelled && <FormMessage kind="success">Consulta cancelada. O horário ficou livre.</FormMessage>}
      {error && <FormMessage kind="error">{error}</FormMessage>}
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

      {data && active && data.can_change && (
        <section aria-label="Alterar a consulta" className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5">
          {data.change_until && (
            <p className="text-sm text-slate-600">
              Podes cancelar ou remarcar na app até <span className="first-letter:uppercase">{formatClinicDay(data.change_until)}</span>, {formatClinicTime(data.change_until)}.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Link
              to={`/patient/consultas/${data.id}/remarcar`}
              className="inline-flex min-h-11 items-center rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
            >
              Remarcar
            </Link>
            <Button variant="secondary" onClick={() => setConfirming(true)}>Cancelar consulta</Button>
          </div>
        </section>
      )}

      {data && active && !data.can_change && (
        <section aria-label="Alterar a consulta" className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
          <p>Já não é possível cancelar ou remarcar esta consulta na app.</p>
          {phone ? (
            <p className="mt-1">Liga para a clínica: <a className="font-semibold underline" href={`tel:${phone.replace(/\s+/g, '')}`}>{phone}</a></p>
          ) : (
            <p className="mt-1">Contacta a clínica.</p>
          )}
        </section>
      )}

      {confirming && data && (
        <ConfirmDialog
          title="Cancelar a consulta?"
          description={`${data.appointment_type} de ${formatClinicDay(data.scheduled_at)}, ${formatClinicTime(data.scheduled_at)}. O horário fica livre para outros pacientes.`}
          confirmLabel="Cancelar consulta"
          isPending={cancel.isPending}
          onConfirm={confirmCancel}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  )
}
