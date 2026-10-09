import { AppointmentRequestsPanel } from '../../components/AppointmentRequestsPanel'
import { useMemo, useState } from 'react'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/TextField'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'
import { useAppointmentsPage, useCancelAppointment, useCreateAppointment, usePatientSearch, usePatients, useStaff, useUpdateAppointment } from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { appointmentCreateSchema, appointmentUpdateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { AppointmentPublic, PatientSummary } from '../../types/api'

export function AppointmentsPage() {
  const { user } = useSession()
  const canCreate = user?.role === 'staff' || user?.role === 'clinic_admin'
  const canHandleReason = user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const appointments = useAppointmentsPage(page, pageSize)
  const appointmentRows = appointments.data?.items
  const total = appointments.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const staff = useStaff()
  const patients = usePatients(canCreate)
  const [selected, setSelected] = useState<AppointmentPublic | null>(null)
  const [feedback, setFeedback] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | AppointmentPublic['status']>('all')

  const staffNameById = useMemo(() => new Map((staff.data ?? []).map((entry) => [entry.id, entry.full_name])), [staff.data])
  const patientNameById = useMemo(() => new Map((patients.data ?? []).map((entry) => [entry.id, entry.full_name])), [patients.data])
  const visibleAppointments = (appointmentRows ?? []).filter((appointment) => statusFilter === 'all' || appointment.status === statusFilter)

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-slate-900">Consultas</h1>
      {feedback && <p role="status" className="text-sm text-teal-700">{feedback}</p>}
      <AppointmentRequestsPanel />
      {canCreate && <CreateAppointmentForm canHandleReason={canHandleReason} />}
      <label className="flex max-w-xs flex-col gap-1 text-sm font-medium text-slate-700">
        Filtrar por estado
        <select aria-label="Filtrar consultas por estado" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)} className="rounded-md border border-slate-300 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-teal-700">
          <option value="all">Todos os estados</option>
          <option value="scheduled">Agendada</option>
          <option value="confirmed">Confirmada</option>
          <option value="completed">Concluída</option>
          <option value="cancelled">Cancelada</option>
          <option value="no_show">Faltou</option>
        </select>
      </label>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />}
        {appointments.isFetching && !appointments.isLoading && <p role="status" className="text-sm text-slate-500">A atualizar consultas…</p>}
        {appointmentRows && appointmentRows.length === 0 && !appointments.isLoading && (
          <EmptyState title="Sem consultas" description="Ainda não existem consultas para mostrar." />
        )}
        {appointmentRows && appointmentRows.length > 0 && visibleAppointments.length === 0 && <EmptyState title="Sem consultas neste estado" description="Experimenta outro filtro." />}
        {visibleAppointments.length > 0 && !appointments.isLoading && (
          <ul className="flex flex-col divide-y divide-slate-100">
            {visibleAppointments.map((appointment) => (
              <li key={appointment.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
                  <p className="text-sm text-slate-500">
                    {user?.role === 'patient'
                      ? `Com ${staffNameById.get(appointment.staff_id) ?? 'profissional'}`
                      : `${patientNameById.get(appointment.patient_id) ?? 'Paciente'} — ${staffNameById.get(appointment.staff_id) ?? 'profissional'}`}
                  </p>
                  {appointment.reason && <p className="text-sm text-slate-600">{appointment.reason}</p>}
                </div>
                <div className="flex items-center gap-3">
                  <AppointmentStatusBadge status={appointment.status} />
                  <Button variant="secondary" onClick={() => setSelected(appointment)}>Detalhes</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {total > pageSize && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
            <span className="text-sm text-slate-500">Página {page} de {pages}</span>
            <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
          </div>
        )}
      </section>
      {selected && (
        <AppointmentDetailDialog
          appointment={appointmentRows?.find((appointment) => appointment.id === selected.id) ?? selected}
          canEdit={canCreate}
          canHandleReason={canHandleReason}
          patientName={patientNameById.get(selected.patient_id) ?? (user?.role === 'patient' ? 'O próprio paciente' : 'Paciente')}
          staffName={staffNameById.get(selected.staff_id) ?? 'Profissional'}
          onClose={() => setSelected(null)}
          onSuccess={(message) => { setFeedback(message); setSelected(null) }}
          onConflict={() => { void appointments.refetch() }}
        />
      )}
    </div>
  )
}

function AppointmentDetailDialog({ appointment, canEdit, canHandleReason, patientName, staffName, onClose, onSuccess, onConflict }: {
  appointment: AppointmentPublic
  canEdit: boolean
  canHandleReason: boolean
  patientName: string
  staffName: string
  onClose: () => void
  onSuccess: (message: string) => void
  onConflict: () => void
}) {
  const cancelAppointment = useCancelAppointment()
  const updateAppointment = useUpdateAppointment()
  const [duration, setDuration] = useState(String(appointment.duration_minutes))
  const [scheduledAt, setScheduledAt] = useState(() => {
    const date = new Date(appointment.scheduled_at)
    return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  })
  const [reason, setReason] = useState(appointment.reason ?? '')
  const [message, setMessage] = useState('')
  const [scheduleErrors, setScheduleErrors] = useState<Record<string, string>>({})
  const scheduleFormRef = useFocusFirstInvalid(scheduleErrors)
  const canChangeSchedule = canEdit && (appointment.status === 'scheduled' || appointment.status === 'confirmed')
  const busy = cancelAppointment.isPending || updateAppointment.isPending

  const [confirmation, setConfirmation] = useState<'cancel' | 'confirm' | 'complete' | 'no_show' | null>(null)

  function conflictAwareError(error: unknown) {
    if (error instanceof ApiError && error.status === 409) {
      setMessage(error.detail ?? 'A consulta foi alterada ou existe um conflito. A agenda será atualizada.')
      onConflict()
      return
    }
    setMessage(toUserMessage(error))
  }

  function saveSchedule(event: React.FormEvent) {
    event.preventDefault()
    setMessage('')
    const result = appointmentUpdateSchema.safeParse({ duration_minutes: duration, reason })
    const errors: Record<string, string> = result.success ? {} : zodErrorsToRecord(result.error)
    if (!scheduledAt || Number.isNaN(new Date(scheduledAt).getTime())) errors.scheduled_at = 'Escolhe data e hora.'
    setScheduleErrors(errors)
    if (!result.success || errors.scheduled_at) return
    updateAppointment.mutate(
      { id: appointment.id, payload: { scheduled_at: new Date(scheduledAt).toISOString(), duration_minutes: result.data.duration_minutes, ...(canHandleReason ? { reason: result.data.reason || null } : {}) } },
      { onSuccess: () => onSuccess('Consulta atualizada.'), onError: conflictAwareError },
    )
  }

  return (
    <>
      <Modal titleId="appointment-detail-title" onClose={onClose}>
        <div className="flex items-start justify-between gap-4">
          <div><h2 id="appointment-detail-title" className="text-lg font-semibold">Detalhe da consulta</h2><p className="text-sm text-slate-500">{formatDateTime(appointment.scheduled_at)}</p></div>
          <button type="button" aria-label="Fechar detalhes" onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100">×</button>
        </div>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          <div><dt className="text-sm text-slate-500">Estado</dt><dd className="mt-1"><AppointmentStatusBadge status={appointment.status} /></dd></div>
          <div><dt className="text-sm text-slate-500">Paciente</dt><dd className="font-medium">{patientName}</dd></div>
          <div><dt className="text-sm text-slate-500">Profissional</dt><dd className="font-medium">{staffName}</dd></div>
        </dl>

        {canChangeSchedule && (
          <form ref={scheduleFormRef} className="mt-5 grid gap-3" onSubmit={saveSchedule} noValidate>
            <TextField label="Data e hora" type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} error={scheduleErrors.scheduled_at} />
            <TextField label="Duração (minutos)" type="number" min={5} max={480} value={duration} onChange={(event) => setDuration(event.target.value)} error={scheduleErrors.duration_minutes} />
            {canHandleReason && <TextField label="Motivo" value={reason} onChange={(event) => setReason(event.target.value)} error={scheduleErrors.reason} />}
            <Button type="submit" isLoading={updateAppointment.isPending}>Guardar alterações</Button>
          </form>
        )}

        {canEdit && appointment.status === 'scheduled' && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setConfirmation('confirm')}>Confirmar</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirmation('cancel')}>Cancelar consulta</Button>
          </div>
        )}
        {canEdit && appointment.status === 'confirmed' && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setConfirmation('complete')}>Concluir</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirmation('no_show')}>Marcar falta</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirmation('cancel')}>Cancelar consulta</Button>
          </div>
        )}
        {message && <p role="alert" className="mt-3 text-sm text-red-600">{message}</p>}
      </Modal>
      {/* A sibling of the modal, not a child: the modal's Escape handler must not close both. */}
      {confirmation && <ConfirmDialog
        title={confirmation === 'cancel' ? 'Cancelar consulta' : confirmation === 'confirm' ? 'Confirmar consulta' : confirmation === 'complete' ? 'Concluir consulta' : 'Marcar falta'}
        description={confirmation === 'cancel' ? 'A consulta será marcada como cancelada.' : 'Esta alteração de estado ficará registada.'}
        confirmLabel={confirmation === 'cancel' ? 'Cancelar consulta' : confirmation === 'confirm' ? 'Confirmar' : confirmation === 'complete' ? 'Concluir' : 'Marcar falta'}
        isPending={busy}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => {
          setMessage('')
          if (confirmation === 'cancel') {
            cancelAppointment.mutate(appointment.id, { onSuccess: () => onSuccess('Consulta cancelada.'), onError: conflictAwareError })
            return
          }
          const status = confirmation === 'confirm' ? 'confirmed' : confirmation === 'complete' ? 'completed' : 'no_show'
          const successMessage = confirmation === 'confirm' ? 'Consulta confirmada.' : confirmation === 'complete' ? 'Consulta concluída.' : 'Falta registada.'
          updateAppointment.mutate(
            { id: appointment.id, payload: { status } },
            { onSuccess: () => onSuccess(successMessage), onError: conflictAwareError },
          )
        }}
      />}
    </>
  )
}

function CreateAppointmentForm({ canHandleReason }: { canHandleReason: boolean }) {
  const createAppointment = useCreateAppointment()
  const staff = useStaff()
  const [patientSearch, setPatientSearch] = useState('')
  const [patientPage, setPatientPage] = useState(1)
  const patientPageSize = 10
  const patients = usePatientSearch(patientSearch, patientPage, patientPageSize)
  const patientResults = patients.data?.items ?? []
  const patientPageCount = Math.max(1, Math.ceil((patients.data?.total ?? 0) / patientPageSize))
  const [form, setForm] = useState({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(fieldErrors)
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
      { ...result.data, scheduled_at: new Date(result.data.scheduled_at).toISOString(), ...(canHandleReason && result.data.reason ? { reason: result.data.reason } : {}) },
      {
        onSuccess: () => {
          setForm({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
          setSelectedPatient(null)
          setPatientSearch('')
          setJustCreated(true)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.fieldErrors) setFieldErrors(error.fieldErrors)
          else setFieldErrors({ _root: toUserMessage(error) })
        },
      },
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium text-slate-900">Marcar consulta</h2>
      <form ref={formRef} onSubmit={handleSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="patient-search" className="text-sm font-medium text-slate-700">Pesquisar paciente</label>
          <input
            type="search"
            id="patient-search"
            value={patientSearch}
            onChange={(event) => { setPatientSearch(event.target.value); setPatientPage(1) }}
            placeholder="Escreve o nome do paciente"
            maxLength={100}
            className="mb-2 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
          />
          <select
            id="patient"
            aria-label="Paciente"
            aria-invalid={Boolean(fieldErrors.patient_id)}
            aria-describedby={fieldErrors.patient_id ? 'patient-error' : undefined}
            value={form.patient_id}
            onChange={(event) => {
              const patientId = event.target.value
              update('patient_id', patientId)
              setSelectedPatient(patientResults.find((patient) => patient.id === patientId) ?? null)
            }}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
          >
            <option value="">{patientSearch.trim() ? 'Escolhe um resultado…' : 'Pesquisa primeiro pelo nome…'}</option>
            {selectedPatient && !patientResults.some((patient) => patient.id === selectedPatient.id) && <option value={selectedPatient.id}>{selectedPatient.full_name}</option>}
            {patientResults.map((patient) => <option key={patient.id} value={patient.id}>{patient.full_name}</option>)}
          </select>
          {patients.isLoading && <p role="status" className="text-sm text-slate-500">A pesquisar pacientes…</p>}
          {patients.isError && <p role="alert" className="text-sm text-red-600">{toUserMessage(patients.error)}</p>}
          {!patients.isLoading && !patients.isError && patientSearch.trim() && patients.data?.total === 0 && <p className="text-sm text-slate-500">Não foram encontrados pacientes com esse nome.</p>}
          {patients.data && patients.data.total > patientPageSize && (
            <div className="flex items-center justify-between gap-2 text-xs text-slate-600">
              <button type="button" className="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-50" disabled={patientPage <= 1 || patients.isFetching} onClick={() => setPatientPage((page) => page - 1)}>Anterior</button>
              <span>Página {patientPage} de {patientPageCount} · {patients.data.total} pacientes</span>
              <button type="button" className="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-50" disabled={patientPage >= patientPageCount || patients.isFetching} onClick={() => setPatientPage((page) => page + 1)}>Seguinte</button>
            </div>
          )}
          {selectedPatient && <p className="text-xs text-slate-600">Paciente selecionado: {selectedPatient.full_name}</p>}
          {fieldErrors.patient_id && <p id="patient-error" role="alert" className="text-sm text-red-600">{fieldErrors.patient_id}</p>}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="staff" className="text-sm font-medium text-slate-700">Profissional</label>
          <select id="staff" aria-invalid={Boolean(fieldErrors.staff_id)} aria-describedby={fieldErrors.staff_id ? 'staff-error' : undefined} value={form.staff_id} onChange={(event) => update('staff_id', event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600">
            <option value="">Escolhe um profissional…</option>
            {(staff.data ?? []).map((entry) => <option key={entry.id} value={entry.id}>{entry.full_name}</option>)}
          </select>
          {staff.isLoading && <p role="status" className="text-sm text-slate-500">A carregar profissionais…</p>}
          {!staff.isLoading && !staff.isError && staff.data?.length === 0 && <p className="text-sm text-slate-500">Não há profissionais ativos para selecionar.</p>}
          {staff.isError && <p role="alert" className="text-sm text-red-600">{toUserMessage(staff.error)}</p>}
          {fieldErrors.staff_id && <p id="staff-error" role="alert" className="text-sm text-red-600">{fieldErrors.staff_id}</p>}
        </div>

        <TextField label="Data e hora" type="datetime-local" value={form.scheduled_at} onChange={(event) => update('scheduled_at', event.target.value)} error={fieldErrors.scheduled_at} />
        <TextField label="Duração (minutos)" type="number" min={5} max={480} value={form.duration_minutes} onChange={(event) => update('duration_minutes', event.target.value)} error={fieldErrors.duration_minutes} />
        {canHandleReason && <TextField label="Motivo (opcional)" value={form.reason} onChange={(event) => update('reason', event.target.value)} />}
        <div className="sm:col-span-2">
          {fieldErrors._root && <p role="alert" className="mb-2 text-sm text-red-600">{fieldErrors._root}</p>}
          {justCreated && <p role="status" className="mb-2 text-sm text-teal-700">Consulta marcada com sucesso.</p>}
          <Button type="submit" isLoading={createAppointment.isPending}>Marcar consulta</Button>
        </div>
      </form>
    </section>
  )
}
