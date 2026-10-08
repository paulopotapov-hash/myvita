import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useStaff } from '../hooks/useClinicData'
import { useSession } from '../hooks/useSession'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import { appointmentRequestsService } from '../services/appointmentRequests'
import type { AppointmentRequestPublic, AppointmentRequestStatus } from '../types/api'
import { Button } from './Button'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'

const REQUESTS_KEY = ['appointment-requests'] as const
const PAGE_SIZE = 20
const STATUS_LABELS: Record<AppointmentRequestStatus, string> = {
  pending: 'Pendente',
  accepted: 'Aceite',
  rejected: 'Recusado',
  cancelled: 'Cancelado',
}
const STATUS_STYLES: Record<AppointmentRequestStatus, string> = {
  pending: 'border-amber-200 bg-amber-50 text-amber-900',
  accepted: 'border-teal-200 bg-teal-50 text-teal-900',
  rejected: 'border-red-200 bg-red-50 text-red-800',
  cancelled: 'border-slate-200 bg-slate-50 text-slate-700',
}

function RequestStatus({ status }: { status: AppointmentRequestStatus }) {
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>
}

/** `datetime-local` value -> ISO with timezone (the backend rejects naive datetimes). */
function toIso(local: string): string {
  return new Date(local).toISOString()
}

/** ISO -> `datetime-local` value in the browser's timezone. */
function toLocalInput(iso: string): string {
  const date = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function useInvalidateRequests() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: REQUESTS_KEY }),
      client.invalidateQueries({ queryKey: ['appointments'] }),
    ])
}

/** Patients request appointments; scheduling staff review them. Hidden for nobody: the
 * backend decides what each role sees and may do. */
export function AppointmentRequestsPanel() {
  const { user } = useSession()
  if (!user) return null
  return user.role === 'patient' ? <PatientRequests /> : <StaffRequests />
}

function PatientRequests() {
  const invalidate = useInvalidateRequests()
  const [preferredStart, setPreferredStart] = useState('')
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState('')
  const [actionError, setActionError] = useState('')
  const requests = useQuery({
    queryKey: [...REQUESTS_KEY, 'mine'],
    queryFn: ({ signal }) => appointmentRequestsService.list(1, PAGE_SIZE, undefined, signal),
  })
  const create = useMutation({ mutationFn: appointmentRequestsService.create, onSuccess: invalidate })
  const cancel = useMutation({ mutationFn: appointmentRequestsService.cancel, onSuccess: invalidate })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setFormError('')
    if (!preferredStart) {
      setFormError('Escolha a data e hora pretendidas.')
      return
    }
    create.mutate(
      { preferred_start: toIso(preferredStart), reason: reason.trim() || undefined },
      {
        onSuccess: () => {
          setPreferredStart('')
          setReason('')
        },
        onError: (error) => setFormError(toUserMessage(error)),
      },
    )
  }

  return (
    <section aria-labelledby="request-heading" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <div>
        <h2 id="request-heading" className="text-lg font-semibold text-slate-900">Pedir consulta</h2>
        <p className="mt-1 text-sm text-slate-600">A clínica escolhe o profissional e confirma a hora. Será notificado da resposta.</p>
      </div>
      <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-[auto_1fr_auto] sm:items-end">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
          Data e hora pretendidas
          <input type="datetime-local" value={preferredStart} onChange={(e) => setPreferredStart(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600" />
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-sm font-medium text-slate-700">
          Motivo (opcional)
          <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600" />
        </label>
        <Button type="submit" isLoading={create.isPending}>Enviar pedido</Button>
      </form>
      {formError && <p role="alert" className="text-sm text-red-700">{formError}</p>}

      <h3 className="text-sm font-semibold text-slate-800">Os meus pedidos</h3>
      {requests.isLoading && <LoadingSpinner label="A carregar pedidos…" />}
      {requests.isError && <ErrorState message={toUserMessage(requests.error)} onRetry={() => requests.refetch()} />}
      {requests.isSuccess && requests.data.items.length === 0 && <p className="text-sm text-slate-600">Ainda não fez pedidos de consulta.</p>}
      {actionError && <p role="alert" className="text-sm text-red-700">{actionError}</p>}
      {requests.data && requests.data.items.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Os meus pedidos de consulta">
          {requests.data.items.map((request) => (
            <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">Preferência: <time dateTime={request.preferred_start}>{formatDateTime(request.preferred_start)}</time></p>
                {request.reason && <p className="break-words text-sm text-slate-600">{request.reason}</p>}
              </div>
              <div className="flex items-center gap-3">
                <RequestStatus status={request.status} />
                {request.status === 'pending' && (
                  <Button
                    variant="secondary"
                    isLoading={cancel.isPending && cancel.variables === request.id}
                    onClick={() => {
                      setActionError('')
                      cancel.mutate(request.id, { onError: (error) => setActionError(toUserMessage(error)) })
                    }}
                  >
                    Cancelar pedido
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
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
  const reject = useMutation({ mutationFn: appointmentRequestsService.reject, onSuccess: invalidate })

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
              onReject={() => {
                setActionError('')
                reject.mutate(request.id, { onError: (error) => setActionError(toUserMessage(error)) })
              }}
              rejecting={reject.isPending && reject.variables === request.id}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

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
  const [open, setOpen] = useState(false)
  const [staffId, setStaffId] = useState('')
  const [scheduledAt, setScheduledAt] = useState(() => toLocalInput(request.preferred_start))
  const [duration, setDuration] = useState(30)
  const [error, setError] = useState('')
  const accept = useMutation({
    mutationFn: () => appointmentRequestsService.accept(request.id, { staff_id: staffId, scheduled_at: toIso(scheduledAt), duration_minutes: duration }),
    onSuccess: onDone,
  })
  const professionals = (staff.data ?? []).filter((member) => member.is_active && (member.staff_role === 'doctor' || member.staff_role === 'nurse'))

  return (
    <li className="flex flex-col gap-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="break-words font-medium text-slate-900">{request.patient_name}</p>
          <p className="text-sm text-slate-600">Preferência: <time dateTime={request.preferred_start}>{formatDateTime(request.preferred_start)}</time></p>
          {request.reason && <p className="break-words text-sm text-slate-600">Motivo: {request.reason}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" aria-expanded={open} onClick={() => setOpen((value) => !value)}>Aceitar…</Button>
          <Button variant="secondary" isLoading={rejecting} onClick={onReject} aria-label={`Recusar pedido de ${request.patient_name}`}>Recusar</Button>
        </div>
      </div>
      {open && (
        <form
          noValidate
          aria-label={`Marcar consulta para ${request.patient_name}`}
          className="grid gap-3 rounded-md bg-slate-50 p-3 sm:grid-cols-4 sm:items-end"
          onSubmit={(event) => {
            event.preventDefault()
            setError('')
            if (!staffId || !scheduledAt) {
              setError('Escolha o profissional e a data.')
              return
            }
            accept.mutate(undefined, { onError: (err) => setError(toUserMessage(err)) })
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
            <input type="number" min={5} max={480} value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <Button type="submit" isLoading={accept.isPending}>Marcar consulta</Button>
          {error && <p role="alert" className="text-sm text-red-700 sm:col-span-4">{error}</p>}
        </form>
      )}
    </li>
  )
}
