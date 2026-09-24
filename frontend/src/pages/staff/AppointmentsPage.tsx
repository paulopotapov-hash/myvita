import { useMemo, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { AppointmentStatusBadge } from '../../components/AppointmentStatusBadge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import {
  useAppointment,
  useAppointments,
  useCancelAppointment,
  useCreateAppointment,
  usePatients,
  useStaff,
  useUpdateAppointment,
} from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { appointmentCreateSchema, appointmentUpdateSchema, zodErrorsToRecord } from '../../lib/validation'
import type { AppointmentPublic, AppointmentStatus } from '../../types/api'

const PAGE_SIZE = 20
const APPOINTMENT_STATUSES: AppointmentStatus[] = ['scheduled', 'confirmed', 'completed', 'cancelled', 'no_show']
const TRANSITIONS: Record<AppointmentStatus, AppointmentStatus[]> = {
  scheduled: ['confirmed', 'cancelled', 'no_show'],
  confirmed: ['completed', 'cancelled', 'no_show'],
  completed: [],
  cancelled: [],
  no_show: [],
}

export function AppointmentsPage() {
  const { user } = useSession()
  const [feedback, setFeedback] = useState('')
  const [searchParams, setSearchParams] = useSearchParams()
  const rawPage = Number.parseInt(searchParams.get('page') ?? '0', 10)
  const page = Number.isFinite(rawPage) ? Math.max(0, rawPage) : 0
  const requestedStatus = searchParams.get('status')
  const filters = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    patient_id: searchParams.get('patient_id') || undefined,
    staff_id: searchParams.get('staff_id') || undefined,
    status: APPOINTMENT_STATUSES.find((status) => status === requestedStatus),
    start_date: toFilterDate(searchParams.get('start_date'), false),
    end_date: toFilterDate(searchParams.get('end_date'), true),
  }
  const appointments = useAppointments(filters)
  const staff = useStaff()
  const canManage = user?.role === 'staff' || user?.role === 'clinic_admin'
  const patients = usePatients(canManage)
  const names = useNames(patients.data, staff.data)

  function updateFilters(next: Record<string, string>) {
    const nextParams = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(next)) {
      if (value) nextParams.set(key, value)
      else nextParams.delete(key)
    }
    nextParams.delete('page')
    setSearchParams(nextParams)
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Consultas</h1>
          <p className="mt-1 text-sm text-slate-500">
            {user?.role === 'patient' ? 'As tuas consultas' : 'Agenda autorizada da clínica'}
          </p>
        </div>
        {canManage && <CreateAppointmentForm onCreated={() => setFeedback('Consulta marcada com sucesso.')} />}
      </header>

      {feedback && <p role="status" className="rounded-md border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{feedback}</p>}

      <AppointmentFilters
        canManage={canManage}
        patientId={filters.patient_id ?? ''}
        staffId={filters.staff_id ?? ''}
        status={filters.status ?? ''}
        startDate={searchParams.get('start_date') ?? ''}
        endDate={searchParams.get('end_date') ?? ''}
        patients={patients.data ?? []}
        staff={staff.data ?? []}
        onChange={updateFilters}
        onClear={() => setSearchParams(new URLSearchParams())}
      />

      <section className="rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
        {appointments.isLoading && <LoadingSpinner />}
        {appointments.isError && (
          <ErrorState message={toUserMessage(appointments.error)} onRetry={() => appointments.refetch()} />
        )}
        {appointments.data && appointments.data.length === 0 && (
          <EmptyState title="Sem consultas" description="Não existem consultas para estes filtros." />
        )}
        {appointments.data && appointments.data.length > 0 && (
          <>
            <ul className="grid gap-3 md:grid-cols-2">
              {appointments.data.map((appointment) => (
                <AppointmentCard key={appointment.id} appointment={appointment} names={names} patient={user?.role === 'patient'} />
              ))}
            </ul>
            <nav aria-label="Paginação de consultas" className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
              <Button variant="secondary" disabled={page === 0 || appointments.isFetching} onClick={() => updatePage(page - 1, searchParams, setSearchParams)}>
                Anterior
              </Button>
              <span className="text-sm text-slate-500">Página {page + 1}</span>
              <Button variant="secondary" disabled={appointments.data.length < PAGE_SIZE || appointments.isFetching} onClick={() => updatePage(page + 1, searchParams, setSearchParams)}>
                Seguinte
              </Button>
            </nav>
          </>
        )}
      </section>
    </div>
  )
}

function updatePage(page: number, current: URLSearchParams, set: (params: URLSearchParams) => void) {
  const params = new URLSearchParams(current)
  if (page) params.set('page', String(page))
  else params.delete('page')
  set(params)
}

function useNames(patients: { id: string; full_name: string }[] | undefined, staff: { id: string; full_name: string }[] | undefined) {
  return useMemo(() => {
    const map = new Map<string, string>()
    for (const person of [...(patients ?? []), ...(staff ?? [])]) map.set(person.id, person.full_name)
    return map
  }, [patients, staff])
}

function AppointmentCard({ appointment, names, patient }: { appointment: AppointmentPublic; names: Map<string, string>; patient: boolean }) {
  return (
    <li className="rounded-lg border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-slate-900">{formatDateTime(appointment.scheduled_at)}</p>
          <p className="mt-1 text-sm text-slate-600">
            {patient ? `Com ${names.get(appointment.staff_id) ?? 'profissional'}` : `${names.get(appointment.patient_id) ?? 'Paciente'} · ${names.get(appointment.staff_id) ?? 'profissional'}`}
          </p>
        </div>
        <AppointmentStatusBadge status={appointment.status} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-sm text-slate-500">
        <span>{appointment.duration_minutes} min{appointment.reason ? ` · ${appointment.reason}` : ''}</span>
        <Link className="font-medium text-teal-700 hover:underline" to={`/app/consultas/${appointment.id}`}>Ver detalhe</Link>
      </div>
    </li>
  )
}

function AppointmentFilters({ canManage, patientId, staffId, status, startDate, endDate, patients, staff, onChange, onClear }: {
  canManage: boolean; patientId: string; staffId: string; status: string; startDate: string; endDate: string
  patients: { id: string; full_name: string }[]; staff: { id: string; full_name: string }[]
  onChange: (next: Record<string, string>) => void
  onClear: () => void
}) {
  const hasFilters = Boolean(patientId || staffId || status || startDate || endDate)
  return (
    <section aria-label="Filtros de consultas" className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {canManage && <SelectField id="patient-filter" label="Paciente" value={patientId} onChange={(value) => onChange({ patient_id: value })} options={patients.map((item) => [item.id, item.full_name])} empty="Todos os pacientes" />}
        {canManage && <SelectField id="staff-filter" label="Profissional" value={staffId} onChange={(value) => onChange({ staff_id: value })} options={staff.map((item) => [item.id, item.full_name])} empty="Todos os profissionais" />}
        <SelectField id="status-filter" label="Estado" value={status} onChange={(value) => onChange({ status: value })} options={Object.entries({ scheduled: 'Agendada', confirmed: 'Confirmada', completed: 'Concluída', cancelled: 'Cancelada', no_show: 'Faltou' })} empty="Todos os estados" />
        <TextField label="A partir de" type="date" value={startDate} onChange={(event) => onChange({ start_date: event.target.value })} />
        <TextField label="Até" type="date" value={endDate} onChange={(event) => onChange({ end_date: event.target.value })} />
      </div>
      {hasFilters && <div className="mt-3 flex justify-end"><Button type="button" variant="secondary" onClick={onClear}>Limpar filtros</Button></div>}
    </section>
  )
}

function SelectField({ id, label, value, onChange, options, empty, error }: { id: string; label: string; value: string; onChange: (value: string) => void; options: [string, string][]; empty: string; error?: string }) {
  const errorId = `${id}-error`
  return <div className="flex flex-col gap-1"><label htmlFor={id} className="text-sm font-medium text-slate-700">{label}</label><select id={id} value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} className={`rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600 ${error ? 'border-red-400' : 'border-slate-300'}`}><option value="">{empty}</option>{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select>{error && <p id={errorId} role="alert" className="text-sm text-red-600">{error}</p>}</div>
}

function CreateAppointmentForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  return <>{!open && <Button onClick={() => setOpen(true)}>Marcar consulta</Button>}{open && <AppointmentForm onClose={() => setOpen(false)} onCreated={() => { setOpen(false); onCreated() }} />}</>
}

function AppointmentForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const create = useCreateAppointment()
  const patients = usePatients()
  const staff = useStaff()
  const [form, setForm] = useState({ patient_id: '', staff_id: '', scheduled_at: '', duration_minutes: '30', reason: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  function submit(event: FormEvent) {
    event.preventDefault()
    const parsed = appointmentCreateSchema.safeParse(form)
    if (!parsed.success) { setErrors(zodErrorsToRecord(parsed.error)); return }
    setErrors({})
    create.mutate({ ...parsed.data, scheduled_at: new Date(parsed.data.scheduled_at).toISOString(), reason: parsed.data.reason || undefined }, { onSuccess: onCreated, onError: (error) => setErrors(error instanceof ApiError && error.fieldErrors ? error.fieldErrors : { _root: toUserMessage(error) }) })
  }
  return <div className="fixed inset-0 z-10 overflow-y-auto bg-slate-900/30 p-4"><section role="dialog" aria-modal="true" aria-labelledby="create-title" className="mx-auto max-w-2xl rounded-xl bg-white p-6 shadow-xl"><div className="flex items-center justify-between"><h2 id="create-title" className="text-lg font-medium text-slate-900">Marcar consulta</h2><button type="button" onClick={onClose} aria-label="Fechar" className="text-2xl text-slate-500">×</button></div>{(patients.isLoading || staff.isLoading) && <LoadingSpinner label="A carregar opções…" />}{(patients.isError || staff.isError) && <p role="alert" className="mt-4 text-sm text-red-600">Não foi possível carregar pacientes ou profissionais. Tenta novamente.</p>}<form onSubmit={submit} noValidate className="mt-4 grid gap-4 sm:grid-cols-2"><SelectField id="create-patient" label="Paciente" value={form.patient_id} onChange={(value) => setForm({ ...form, patient_id: value })} options={(patients.data ?? []).map((item) => [item.id, item.full_name])} empty="Escolhe um paciente" error={errors.patient_id} /> <SelectField id="create-staff" label="Profissional" value={form.staff_id} onChange={(value) => setForm({ ...form, staff_id: value })} options={(staff.data ?? []).map((item) => [item.id, item.full_name])} empty="Escolhe um profissional" error={errors.staff_id} /><TextField label="Data e hora (hora local)" type="datetime-local" value={form.scheduled_at} onChange={(event) => setForm({ ...form, scheduled_at: event.target.value })} error={errors.scheduled_at} /><TextField label="Duração (minutos)" type="number" min="5" max="480" value={form.duration_minutes} onChange={(event) => setForm({ ...form, duration_minutes: event.target.value })} error={errors.duration_minutes} /><TextField label="Motivo (opcional)" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} error={errors.reason} /><div className="sm:col-span-2">{errors._root && <p role="alert" className="mb-3 text-sm text-red-600">{errors._root}</p>}<div className="flex gap-2"><Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button><Button type="submit" isLoading={create.isPending} disabled={patients.isLoading || staff.isLoading || patients.isError || staff.isError}>Marcar consulta</Button></div></div></form></section></div>
}

export function AppointmentDetailPage() {
  const { appointmentId: routeAppointmentId } = useParams<{ appointmentId: string }>()
  const { user } = useSession()
  const query = useAppointment(routeAppointmentId)
  const staff = useStaff()
  const patients = usePatients(user?.role !== 'patient')
  const update = useUpdateAppointment()
  const cancel = useCancelAppointment()
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [editing, setEditing] = useState(false)
  const appointment = query.data
  const names = useNames(patients.data, staff.data)
  const canManage = user?.role === 'staff' || user?.role === 'clinic_admin'
  if (query.isLoading) return <LoadingSpinner />
  if (query.isError || !appointment) return <ErrorState message={toUserMessage(query.error)} onRetry={() => query.refetch()} />
  const appointmentId = appointment.id
  const transitions = canManage ? TRANSITIONS[appointment.status] : []
  async function changeStatus(status: AppointmentStatus) {
    if (status === 'cancelled' && !window.confirm('Queres cancelar esta consulta?')) return
    setFeedback(null)
    await update.mutateAsync({ id: appointmentId, payload: { status } }).then(() => setFeedback({ kind: 'success', text: 'Estado atualizado.' })).catch((error) => setFeedback({ kind: 'error', text: toUserMessage(error) }))
  }
  function cancelAppointment() {
    if (!window.confirm('Queres cancelar esta consulta?')) return
    setFeedback(null)
    cancel.mutate(appointmentId, { onSuccess: () => setFeedback({ kind: 'success', text: 'Consulta cancelada.' }), onError: (error) => setFeedback({ kind: 'error', text: toUserMessage(error) }) })
  }
  return <div className="mx-auto flex max-w-3xl flex-col gap-6"><Link to="/app/consultas" className="text-sm font-medium text-teal-700 hover:underline">← Voltar às consultas</Link><header className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold text-slate-900">Detalhe da consulta</h1><p className="mt-1 text-slate-600">{formatDateTime(appointment.scheduled_at)} · {appointment.duration_minutes} min</p></div><AppointmentStatusBadge status={appointment.status} /></header><dl className="grid gap-4 rounded-xl border border-slate-200 bg-white p-6 sm:grid-cols-2"><Info label="Paciente" value={user?.role === 'patient' ? 'Tu' : names.get(appointment.patient_id) ?? 'Paciente'} /><Info label="Profissional" value={names.get(appointment.staff_id) ?? 'Profissional'} /><Info label="Motivo" value={appointment.reason ?? 'Não indicado'} /></dl>{feedback && <p role={feedback.kind === 'error' ? 'alert' : 'status'} className={`rounded-md p-3 text-sm ${feedback.kind === 'error' ? 'bg-red-50 text-red-700' : 'bg-teal-50 text-teal-800'}`}>{feedback.text}</p>}{canManage && transitions.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-6"><h2 className="font-medium text-slate-900">Ações de estado</h2><div className="mt-3 flex flex-wrap gap-2">{transitions.map((status) => <Button key={status} variant={status === 'cancelled' ? 'secondary' : 'primary'} disabled={update.isPending} onClick={() => void changeStatus(status)}>{status === 'confirmed' ? 'Confirmar' : status === 'completed' ? 'Concluir' : status === 'no_show' ? 'Marcar falta' : 'Cancelar consulta'}</Button>)}</div></section>}{user?.role === 'patient' && (appointment.status === 'scheduled' || appointment.status === 'confirmed') && <Button variant="secondary" disabled={cancel.isPending} isLoading={cancel.isPending} onClick={cancelAppointment}>Cancelar consulta</Button>}{canManage && <Button variant="secondary" onClick={() => setEditing(!editing)}>{editing ? 'Fechar edição' : 'Editar consulta'}</Button>}{editing && canManage && <EditAppointment appointment={appointment} onDone={() => { setEditing(false); setFeedback({ kind: 'success', text: 'Consulta atualizada.' }) }} />}</div>
}

function EditAppointment({ appointment, onDone }: { appointment: AppointmentPublic; onDone: () => void }) {
  const update = useUpdateAppointment()
  const [scheduledAt, setScheduledAt] = useState(toLocalInput(appointment.scheduled_at))
  const [duration, setDuration] = useState(String(appointment.duration_minutes))
  const [reason, setReason] = useState(appointment.reason ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})
  function submit(event: FormEvent) { event.preventDefault(); const parsed = appointmentUpdateSchema.safeParse({ scheduled_at: scheduledAt, duration_minutes: duration, reason }); if (!parsed.success) { setErrors(zodErrorsToRecord(parsed.error)); return } setErrors({}); update.mutate({ id: appointment.id, payload: { scheduled_at: new Date(parsed.data.scheduled_at).toISOString(), duration_minutes: parsed.data.duration_minutes, reason: parsed.data.reason || null } }, { onSuccess: onDone, onError: (error) => setErrors({ _root: toUserMessage(error) }) }) }
  return <form onSubmit={submit} noValidate className="grid gap-4 rounded-xl border border-slate-200 bg-white p-6 sm:grid-cols-3"><TextField label="Data e hora (hora local)" type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} error={errors.scheduled_at} /><TextField label="Duração (minutos)" type="number" min="5" max="480" value={duration} onChange={(event) => setDuration(event.target.value)} error={errors.duration_minutes} /><TextField label="Motivo" value={reason} onChange={(event) => setReason(event.target.value)} error={errors.reason} /><div className="sm:col-span-3">{errors._root && <p role="alert" className="mb-3 text-sm text-red-600">{errors._root}</p>}<Button type="submit" isLoading={update.isPending}>Guardar alterações</Button></div></form>
}

function Info({ label, value }: { label: string; value: string }) { return <div><dt className="text-sm text-slate-500">{label}</dt><dd className="mt-1 break-words font-medium text-slate-900">{value}</dd></div> }
function toFilterDate(value: string | null, end: boolean) {
  if (!value) return undefined
  return new Date(`${value}T${end ? '23:59:59.999' : '00:00:00'}`).toISOString()
}
function toLocalInput(iso: string) { const date = new Date(iso); const pad = (value: number) => String(value).padStart(2, '0'); return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}` }
