import { useMemo, useState } from 'react'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { SelectField } from '../../components/SelectField'
import { TextField } from '../../components/TextField'
import { useAppointments, useCancelAppointment, useCreateAppointment, usePatients, useStaff, useUpdateAppointment } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { appointmentCreateSchema, appointmentUpdateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { AppointmentPublic } from '../../types/api'

export function AppointmentsPage() {
  const { user } = useSession()
  const canCreate = user?.role === 'staff' || user?.role === 'clinic_admin'
  const canHandleReason = user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
  const appointments = useAppointments()
  const staff = useStaff()
  const patients = usePatients(canCreate)
  const [selected, setSelected] = useState<AppointmentPublic | null>(null)
  const [notice, setNotice] = useState('')

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

      {canCreate && <CreateAppointmentForm canHandleReason={canHandleReason} onCreated={() => setNotice('')} />}
      {notice && <FormMessage kind="success">{notice}</FormMessage>}

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
                  <Button variant="secondary" onClick={() => { setNotice(''); setSelected(appointment) }}>Detalhes</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      {selected && (
        <AppointmentDetailDialog appointment={selected} canEdit={canCreate} canHandleReason={canHandleReason} patientName={patientNameById.get(selected.patient_id) ?? 'O próprio paciente'} staffName={staffNameById.get(selected.staff_id) ?? 'Profissional'} onClose={() => setSelected(null)} onDone={setNotice} />
      )}
    </div>
  )
}

function AppointmentDetailDialog({ appointment, canEdit, canHandleReason, patientName, staffName, onClose, onDone }: { appointment: AppointmentPublic; canEdit: boolean; canHandleReason: boolean; patientName: string; staffName: string; onClose: () => void; onDone: (message: string) => void }) {
  const updateAppointment = useUpdateAppointment()
  const cancelAppointment = useCancelAppointment()
  const [duration, setDuration] = useState(String(appointment.duration_minutes))
  const [reason, setReason] = useState(appointment.reason ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const busy = updateAppointment.isPending || cancelAppointment.isPending
  const mutable = canEdit && (appointment.status === 'scheduled' || appointment.status === 'confirmed')

  function save(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    const result = appointmentUpdateSchema.safeParse({ duration_minutes: duration, reason })
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    updateAppointment.mutate(
      { id: appointment.id, payload: { duration_minutes: result.data.duration_minutes, ...(canHandleReason ? { reason: result.data.reason || null } : {}) } },
      {
        onSuccess: () => { onDone('Consulta atualizada.'); onClose() },
        onError: (error) => setErrors(formErrorsFrom(error, ['duration_minutes', 'reason'])),
      },
    )
  }

  function cancel() {
    if (busy) return
    if (!window.confirm('Cancelar esta consulta?')) return
    setErrors({})
    cancelAppointment.mutate(appointment.id, {
      onSuccess: () => { onDone('Consulta cancelada.'); onClose() },
      onError: (error) => setErrors({ _root: toUserMessage(error) }),
    })
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="appointment-detail-title" className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/40 p-4">
      <section className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4"><div><h2 id="appointment-detail-title" className="text-lg font-semibold">Detalhe da consulta</h2><p className="text-sm text-slate-500">{formatDateTime(appointment.scheduled_at)}</p></div><button type="button" aria-label="Fechar detalhes" onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100">×</button></div>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-slate-500">Estado</dt><dd className="mt-1"><AppointmentStatusBadge status={appointment.status} /></dd></div><div><dt className="text-sm text-slate-500">Paciente</dt><dd className="font-medium">{patientName}</dd></div><div><dt className="text-sm text-slate-500">Profissional</dt><dd className="font-medium">{staffName}</dd></div></dl>
        {mutable ? (
          <form className="mt-5 grid gap-3" onSubmit={save} noValidate>
            <TextField label="Duração (minutos)" type="number" min={5} max={480} value={duration} onChange={(event) => setDuration(event.target.value)} error={errors.duration_minutes} />
            {canHandleReason && <TextField label="Motivo" value={reason} onChange={(event) => setReason(event.target.value)} error={errors.reason} maxLength={500} />}
            {errors._root && <FormMessage kind="error">{errors._root}</FormMessage>}
            <div className="flex flex-wrap gap-3">
              <Button type="submit" isLoading={updateAppointment.isPending} disabled={busy}>Guardar alterações</Button>
              <Button variant="secondary" isLoading={cancelAppointment.isPending} disabled={busy} onClick={cancel}>Cancelar consulta</Button>
            </div>
          </form>
        ) : <p className="mt-5 text-sm text-slate-600">{appointment.reason ? `${appointment.reason} · ` : ''}{appointment.duration_minutes} minutos</p>}
      </section>
    </div>
  )
}

function CreateAppointmentForm({ canHandleReason, onCreated }: { canHandleReason: boolean; onCreated: () => void }) {
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
    if (createAppointment.isPending) return
    setJustCreated(false)
    onCreated()
    const result = appointmentCreateSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    const { reason, ...rest } = result.data
    createAppointment.mutate(
      {
        ...rest,
        scheduled_at: new Date(rest.scheduled_at).toISOString(),
        // The backend answers 403 to any `reason` from non-clinical roles, even an empty one.
        ...(canHandleReason && reason ? { reason } : {}),
      },
      {
        onSuccess: () => {
          setForm({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
          setJustCreated(true)
        },
        onError: (error) => setFieldErrors(formErrorsFrom(error, ['patient_id', 'staff_id', 'scheduled_at', 'duration_minutes', 'reason'])),
      },
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium text-slate-900">Marcar consulta</h2>
      <form onSubmit={handleSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Paciente" value={form.patient_id} onChange={(e) => update('patient_id', e.target.value)} error={fieldErrors.patient_id}>
          <option value="">Escolhe um paciente…</option>
          {(patients.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </SelectField>
        <SelectField label="Profissional" value={form.staff_id} onChange={(e) => update('staff_id', e.target.value)} error={fieldErrors.staff_id}>
          <option value="">Escolhe um profissional…</option>
          {(staff.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.full_name}
            </option>
          ))}
        </SelectField>

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
        {canHandleReason && <TextField
          label="Motivo (opcional)"
          value={form.reason}
          onChange={(e) => update('reason', e.target.value)}
          error={fieldErrors.reason}
          maxLength={500}
        />}

        <div className="sm:col-span-2">
          {fieldErrors._root && <FormMessage kind="error" className="mb-2">{fieldErrors._root}</FormMessage>}
          {justCreated && <FormMessage kind="success" className="mb-2">Consulta marcada com sucesso.</FormMessage>}
          <Button type="submit" isLoading={createAppointment.isPending}>
            Marcar consulta
          </Button>
        </div>
      </form>
    </section>
  )
}
