import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useStaff } from '../hooks/useClinicData'
import { useSession } from '../hooks/useSession'
import { describePreferences, OPEN_REQUEST_STATUSES, REQUEST_STATUS_LABELS, requestTitle } from '../lib/appointmentRequests'
import { clinicLocalToIso, formatClinicDay, formatClinicTime } from '../lib/clinicTime'
import { toUserMessage } from '../lib/errorMessages'
import { appointmentRequestsService } from '../services/appointmentRequests'
import type { AppointmentRequestPublic, AppointmentRequestStatus } from '../types/api'
import { Button } from './Button'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'

const REQUESTS_KEY = ['appointment-requests'] as const
const PAGE_SIZE = 20
const STATUS_STYLES: Record<AppointmentRequestStatus, string> = {
  pending: 'border-amber-200 bg-amber-50 text-amber-900',
  proposed: 'border-sky-200 bg-sky-50 text-sky-900',
  accepted: 'border-teal-200 bg-teal-50 text-teal-900',
  rejected: 'border-red-200 bg-red-50 text-red-800',
  cancelled: 'border-slate-200 bg-slate-50 text-slate-700',
  declined: 'border-slate-200 bg-slate-50 text-slate-700',
}

function RequestStatus({ status }: { status: AppointmentRequestStatus }) {
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>{REQUEST_STATUS_LABELS[status]}</span>
}

function when(iso: string): string {
  return `${formatClinicDay(iso)}, ${formatClinicTime(iso)}`
}

/** ISO -> Lisbon wall clock "YYYY-MM-DDTHH:MM" for a datetime-local field. */
function toClinicInput(iso: string): string {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Lisbon', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso))
  return `${day}T${formatClinicTime(iso)}`
}

function useInvalidateRequests() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: REQUESTS_KEY }),
      client.invalidateQueries({ queryKey: ['appointments'] }),
    ])
}

/** Patients follow and answer their requests; scheduling staff decide on them. The
 * backend decides what each role sees and may do. */
export function AppointmentRequestsPanel() {
  const { user } = useSession()
  if (!user) return null
  return user.role === 'patient' ? <PatientRequests /> : <StaffRequests />
}

function PatientRequests() {
  const invalidate = useInvalidateRequests()
  const [actionError, setActionError] = useState('')
  const requests = useQuery({
    queryKey: [...REQUESTS_KEY, 'mine'],
    queryFn: ({ signal }) => appointmentRequestsService.list(1, PAGE_SIZE, undefined, signal),
  })
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'cancel' | 'acceptProposal' | 'declineProposal' }) =>
      appointmentRequestsService[action](id),
    onSettled: invalidate,
  })
  const items = requests.data?.items ?? []
  const open = items.filter((request) => OPEN_REQUEST_STATUSES.includes(request.status))
  const closed = items.filter((request) => !OPEN_REQUEST_STATUSES.includes(request.status))
  const run = (id: string, action: 'cancel' | 'acceptProposal' | 'declineProposal') => {
    setActionError('')
    act.mutate({ id, action }, { onError: (error) => setActionError(toUserMessage(error)) })
  }
  const busy = (id: string, action: string) => act.isPending && act.variables?.id === id && act.variables.action === action

  if (requests.isSuccess && items.length === 0) return null
  return (
    <section aria-labelledby="request-heading" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <h2 id="request-heading" className="text-lg font-semibold text-slate-900">Os meus pedidos</h2>
      {requests.isLoading && <LoadingSpinner label="A carregar pedidos…" />}
      {requests.isError && <ErrorState message={toUserMessage(requests.error)} onRetry={() => requests.refetch()} />}
      {actionError && <p role="alert" className="text-sm text-red-700">{actionError}</p>}
      {open.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Pedidos em curso">
          {open.map((request) => (
            <li key={request.id} className="flex flex-col gap-3 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{requestTitle(request)}</p>
                  {request.reschedule_of_start && <p className="text-sm text-slate-600">Consulta de {when(request.reschedule_of_start)}</p>}
                  <p className="text-sm text-slate-600">Preferência: {describePreferences(request)}{request.staff_name ? ` · ${request.staff_name}` : ''}</p>
                </div>
                <RequestStatus status={request.status} />
              </div>
              {request.status === 'proposed' && request.proposed_start && (
                <div className="flex flex-col gap-3 rounded-md border border-sky-200 bg-sky-50 p-3">
                  <p className="text-sm text-sky-950">
                    A clínica propõe: <strong className="first-letter:uppercase">{when(request.proposed_start)}</strong>
                    {request.proposed_staff_name && <> com <strong>{request.proposed_staff_name}</strong></>}.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button isLoading={busy(request.id, 'acceptProposal')} onClick={() => run(request.id, 'acceptProposal')}>Aceitar proposta</Button>
                    <Button variant="secondary" isLoading={busy(request.id, 'declineProposal')} onClick={() => run(request.id, 'declineProposal')}>Recusar proposta</Button>
                  </div>
                </div>
              )}
              <div>
                <Button variant="secondary" isLoading={busy(request.id, 'cancel')} onClick={() => run(request.id, 'cancel')}>Cancelar pedido</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {closed.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-slate-700">Pedidos anteriores ({closed.length})</summary>
          <ul className="divide-y divide-slate-100" aria-label="Pedidos anteriores">
            {closed.map((request) => (
              <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{requestTitle(request)}</p>
                  <p className="text-sm text-slate-600">{describePreferences(request)}</p>
                </div>
                <RequestStatus status={request.status} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function StaffRequests() {
  const invalidate = useInvalidateRequests()
  const [actionError, setActionError] = useState('')
  const pending = useQuery({
    queryKey: [...REQUESTS_KEY, 'pending'],
    queryFn: ({ signal }) => appointmentRequestsService.list(1, PAGE_SIZE, 'pending', signal),
  })
  const proposed = useQuery({
    queryKey: [...REQUESTS_KEY, 'proposed'],
    queryFn: ({ signal }) => appointmentRequestsService.list(1, PAGE_SIZE, 'proposed', signal),
  })
  const reject = useMutation({ mutationFn: appointmentRequestsService.reject, onSuccess: invalidate })
  const onReject = (request: AppointmentRequestPublic) => {
    setActionError('')
    reject.mutate(request.id, { onError: (error) => setActionError(toUserMessage(error)) })
  }

  return (
    <section aria-labelledby="pending-requests-heading" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <h2 id="pending-requests-heading" className="text-lg font-semibold text-slate-900">
        Pedidos de consulta pendentes
        {pending.data && pending.data.total > 0 && <span className="ml-2 text-sm font-normal text-slate-600">({pending.data.total})</span>}
      </h2>
      {pending.isLoading && <LoadingSpinner label="A carregar pedidos…" />}
      {pending.isError && <ErrorState message={toUserMessage(pending.error)} onRetry={() => pending.refetch()} />}
      {pending.isSuccess && pending.data.items.length === 0 && <p className="text-sm text-slate-600">Não há pedidos pendentes.</p>}
      {actionError && <p role="alert" className="text-sm text-red-700">{actionError}</p>}
      {pending.data && pending.data.items.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Pedidos de consulta pendentes">
          {pending.data.items.map((request) => (
            <PendingRequest
              key={request.id}
              request={request}
              onDone={invalidate}
              onReject={() => onReject(request)}
              rejecting={reject.isPending && reject.variables === request.id}
            />
          ))}
        </ul>
      )}
      {proposed.data && proposed.data.items.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-slate-800">Propostas à espera do paciente</h3>
          <ul className="divide-y divide-slate-100" aria-label="Propostas à espera do paciente">
            {proposed.data.items.map((request) => (
              <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="break-words font-medium text-slate-900">{request.patient_name}</p>
                  <p className="text-sm text-slate-600">{requestTitle(request)}</p>
                  {request.proposed_start && (
                    <p className="text-sm text-slate-600">Proposto: <span className="first-letter:uppercase">{when(request.proposed_start)}</span>{request.proposed_staff_name ? ` · ${request.proposed_staff_name}` : ''}</p>
                  )}
                </div>
                <Button
                  variant="secondary"
                  isLoading={reject.isPending && reject.variables === request.id}
                  onClick={() => onReject(request)}
                  aria-label={`Retirar proposta a ${request.patient_name}`}
                >
                  Retirar proposta
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

type Decision = 'accept' | 'propose'

function PendingRequest({
  request,
  onDone,
  onReject,
  rejecting,
}: {
  request: AppointmentRequestPublic
  onDone: () => unknown
  onReject: () => void
  rejecting: boolean
}) {
  const staff = useStaff()
  const [open, setOpen] = useState<Decision | null>(null)
  const [staffId, setStaffId] = useState(request.staff_id ?? '')
  const [scheduledAt, setScheduledAt] = useState(() => (request.preferred_start ? toClinicInput(request.preferred_start) : ''))
  const [duration, setDuration] = useState('')
  const [error, setError] = useState('')
  const decide = useMutation({
    mutationFn: (decision: Decision) => {
      const payload = { staff_id: staffId, scheduled_at: clinicLocalToIso(scheduledAt), ...(duration ? { duration_minutes: Number(duration) } : {}) }
      return decision === 'accept' ? appointmentRequestsService.accept(request.id, payload) : appointmentRequestsService.propose(request.id, payload)
    },
    onSuccess: onDone,
  })
  const professionals = (staff.data ?? []).filter((member) => member.is_active && (member.staff_role === 'doctor' || member.staff_role === 'nurse'))
  const toggle = (decision: Decision) => setOpen((current) => (current === decision ? null : decision))

  return (
    <li className="flex flex-col gap-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="break-words font-medium text-slate-900">{request.patient_name}</p>
          <p className="text-sm text-slate-600">{requestTitle(request)}</p>
          {request.reschedule_of_start && <p className="text-sm text-slate-600">Consulta atual: <span className="first-letter:uppercase">{when(request.reschedule_of_start)}</span></p>}
          <p className="text-sm text-slate-600">Preferência: {describePreferences(request)}{request.staff_name ? ` · ${request.staff_name}` : ''}</p>
          {request.reason && <p className="break-words text-sm text-slate-600">Motivo: {request.reason}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" aria-expanded={open === 'accept'} onClick={() => toggle('accept')}>Aceitar…</Button>
          <Button variant="secondary" aria-expanded={open === 'propose'} onClick={() => toggle('propose')}>Propor horário…</Button>
          <Button variant="secondary" isLoading={rejecting} onClick={onReject} aria-label={`Recusar pedido de ${request.patient_name}`}>Recusar</Button>
        </div>
      </div>
      {open && (
        <form
          noValidate
          aria-label={open === 'accept' ? `Marcar consulta para ${request.patient_name}` : `Propor horário a ${request.patient_name}`}
          className="grid gap-3 rounded-md bg-slate-50 p-3 sm:grid-cols-4 sm:items-end"
          onSubmit={(event) => {
            event.preventDefault()
            setError('')
            if (!staffId || !scheduledAt) {
              setError('Escolha o profissional e a data.')
              return
            }
            decide.mutate(open, { onError: (err) => setError(toUserMessage(err)) })
          }}
        >
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Profissional
            <select value={staffId} onChange={(e) => setStaffId(e.target.value)} className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="">Escolha</option>
              {professionals.map((member) => <option key={member.id} value={member.id}>{member.full_name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Data e hora
            <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Duração (min)
            <input type="number" min={5} max={480} value={duration} placeholder={request.appointment_type ? 'Do tipo' : '30'} onChange={(e) => setDuration(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <Button type="submit" isLoading={decide.isPending}>{open === 'accept' ? 'Marcar consulta' : 'Enviar proposta'}</Button>
          {error && <p role="alert" className="text-sm text-red-700 sm:col-span-4">{error}</p>}
        </form>
      )}
    </li>
  )
}
