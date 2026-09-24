import { useMemo, useState } from 'react'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useAppointments, useCancelAppointment, useCreateAppointment, usePatients, useStaff, useUpdateAppointment } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { appointmentCreateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { AppointmentPublic } from '../../types/api'

export function AppointmentsPage() {
  const { user } = useSession()
  const canCreate = user?.role === 'staff' || user?.role === 'clinic_admin'
  const appointments = useAppointments()
  const staff = useStaff()
  const patients = usePatients(canCreate)
  const [selected, setSelected] = useState<AppointmentPublic | null>(null)

  const staffNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const s of staff.data ?? []) map.set(s.id, s.full_name)
    return map
  }, [staff.data])

  const patientNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of patients.data ?? []) map.set(p.id, p.full_name)
    return map
  }, [patients.data])

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Consultas</h1>

      {canCreate && <CreateAppointmentForm />}

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && appointments.data.length === 0 && (
          <EmptyState title="Sem consultas" description="Ainda não existem consultas para mostrar." />
        )}
        {appointments.data && appointments.data.length > 0 && (
          <ul className="flex flex-col divide-y divide-slate-100">
            {appointments.data.map((appointment) => (
              <li key={appointment.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
                  <p className="text-sm text-slate-500">
                    {user?.role === 'patient'
                      ? `Com ${staffNameById.get(appointment.staff_id) ?? 'profissional'}`
                      : `${patientNameById.get(appointment.patient_id) ?? 'Paciente'} — ${
                          staffNameById.get(appointment.staff_id) ?? 'profissional'
                        }`}
                  </p>
                  {appointment.reason && <p className="text-sm text-slate-400">{appointment.reason}</p>}
                </div>
                <div className="flex items-center gap-3">
                  <AppointmentStatusBadge status={appointment.status} />
                  <Button variant="secondary" onClick={() => setSelected(appointment)}>Detalhes</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      {selected && (
        <AppointmentDetailDialog appointment={selected} canEdit={canCreate} patientName={patientNameById.get(selected.patient_id) ?? 'O próprio paciente'} staffName={staffNameById.get(selected.staff_id) ?? 'Profissional'} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function AppointmentDetailDialog({ appointment, canEdit, patientName, staffName, onClose }: { appointment: AppointmentPublic; canEdit: boolean; patientName: string; staffName: string; onClose: () => void }) {
  const updateAppointment = useUpdateAppointment()
  const cancelAppointment = useCancelAppointment()
  const [duration, setDuration] = useState(String(appointment.duration_minutes))
  const [reason, setReason] = useState(appointment.reason ?? '')
  const [message, setMessage] = useState('')
  const mutable = canEdit && (appointment.status === 'scheduled' || appointment.status === 'confirmed')
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="appointment-detail-title" className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/40 p-4">
      <section className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4"><div><h2 id="appointment-detail-title" className="text-lg font-semibold">Detalhe da consulta</h2><p className="text-sm text-slate-500">{formatDateTime(appointment.scheduled_at)}</p></div><button type="button" aria-label="Fechar detalhes" onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100">×</button></div>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-slate-500">Estado</dt><dd className="mt-1"><AppointmentStatusBadge status={appointment.status} /></dd></div><div><dt className="text-sm text-slate-500">Paciente</dt><dd className="font-medium">{patientName}</dd></div><div><dt className="text-sm text-slate-500">Profissional</dt><dd className="font-medium">{staffName}</dd></div></dl>
        {mutable ? <form className="mt-5 grid gap-3" onSubmit={(event) => { event.preventDefault(); setMessage(''); const minutes = Number(duration); if (!Number.isInteger(minutes) || minutes < 5 || minutes > 480) { setMessage('A duração deve estar entre 5 e 480 minutos.'); return } updateAppointment.mutate({ id: appointment.id, payload: { duration_minutes: minutes, reason: reason || null } }, { onSuccess: () => { setMessage('Consulta atualizada.'); onClose() }, onError: (error) => setMessage(toUserMessage(error)) }) }}><TextField label="Duração (minutos)" type="number" min={5} max={480} value={duration} onChange={(event) => setDuration(event.target.value)} /><TextField label="Motivo" value={reason} onChange={(event) => setReason(event.target.value)} /><div className="flex flex-wrap gap-3"><Button type="submit" isLoading={updateAppointment.isPending}>Guardar alterações</Button><Button variant="secondary" disabled={cancelAppointment.isPending} onClick={() => { if (!window.confirm('Cancelar esta consulta?')) return; cancelAppointment.mutate(appointment.id, { onSuccess: onClose, onError: (error) => setMessage(toUserMessage(error)) }) }}>Cancelar consulta</Button></div>{message && <p role="alert" className="text-sm text-red-600">{message}</p>}</form> : <p className="mt-5 text-sm text-slate-600">{appointment.reason ?? 'Sem motivo indicado'} · {appointment.duration_minutes} minutos</p>}
      </section>
    </div>
  )
}

function CreateAppointmentForm() {
  const createAppointment = useCreateAppointment()
  const patients = usePatients()
  const staff = useStaff()

  const [form, setForm] = useState({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [justCreated, setJustCreated] = useState(false)

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setJustCreated(false)
    const result = appointmentCreateSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    createAppointment.mutate(
      {
        ...result.data,
        scheduled_at: new Date(result.data.scheduled_at).toISOString(),
        reason: result.data.reason || undefined,
      },
      {
        onSuccess: () => {
          setForm({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
          setJustCreated(true)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.fieldErrors) {
            setFieldErrors(error.fieldErrors)
          } else {
            setFieldErrors({ _root: toUserMessage(error) })
          }
        },
      },
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium text-slate-900">Marcar consulta</h2>
      <form onSubmit={handleSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="patient" className="text-sm font-medium text-slate-700">
            Paciente
          </label>
          <select
            id="patient"
            value={form.patient_id}
            onChange={(e) => update('patient_id', e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
          >
            <option value="">Escolhe um paciente…</option>
            {(patients.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
          {fieldErrors.patient_id && (
            <p role="alert" className="text-sm text-red-600">
              {fieldErrors.patient_id}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="staff" className="text-sm font-medium text-slate-700">
            Profissional
          </label>
          <select
            id="staff"
            value={form.staff_id}
            onChange={(e) => update('staff_id', e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
          >
            <option value="">Escolhe um profissional…</option>
            {(staff.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </select>
          {fieldErrors.staff_id && (
            <p role="alert" className="text-sm text-red-600">
              {fieldErrors.staff_id}
            </p>
          )}
        </div>

        <TextField
          label="Data e hora"
          type="datetime-local"
          value={form.scheduled_at}
          onChange={(e) => update('scheduled_at', e.target.value)}
          error={fieldErrors.scheduled_at}
        />
        <TextField
          label="Duração (minutos)"
          type="number"
          min={5}
          max={480}
          value={form.duration_minutes}
          onChange={(e) => update('duration_minutes', e.target.value)}
          error={fieldErrors.duration_minutes}
        />
        <TextField
          label="Motivo (opcional)"
          value={form.reason}
          onChange={(e) => update('reason', e.target.value)}
        />

        <div className="sm:col-span-2">
          {fieldErrors._root && (
            <p role="alert" className="mb-2 text-sm text-red-600">
              {fieldErrors._root}
            </p>
          )}
          {justCreated && <p className="mb-2 text-sm text-teal-700">Consulta marcada com sucesso.</p>}
          <Button type="submit" isLoading={createAppointment.isPending}>
            Marcar consulta
          </Button>
        </div>
      </form>
    </section>
  )
}
