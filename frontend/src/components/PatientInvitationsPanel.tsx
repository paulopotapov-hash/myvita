import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../lib/apiClient'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import { patientInvitationSchema, zodErrorsToRecord } from '../lib/validation'
import { invitationsService } from '../services/invitations'
import { Button } from './Button'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'
import { TextField } from './TextField'

const INVITATIONS_KEY = ['invitations', 'pending'] as const
const PAGE_SIZE = 20
const EMPTY_FORM = { full_name: '', email: '' }

/**
 * Patient onboarding by invitation (clinic admins, doctors, nurses). The
 * backend binds the new account to the caller's clinic; the one-time link is
 * kept only in component state and is never stored or listed again.
 */
export function PatientInvitationsPanel() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [invitationLink, setInvitationLink] = useState('')
  const [copied, setCopied] = useState(false)
  const [actionError, setActionError] = useState('')

  const pending = useQuery({
    queryKey: INVITATIONS_KEY,
    queryFn: ({ signal }) => invitationsService.listPending(1, PAGE_SIZE, signal),
  })
  const invite = useMutation({
    mutationFn: invitationsService.invitePatient,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY }),
  })
  const revoke = useMutation({
    mutationFn: invitationsService.revoke,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY }),
  })
  const patientInvitations = pending.data?.items.filter((item) => item.role === 'patient') ?? []

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setInvitationLink('')
    setCopied(false)
    const result = patientInvitationSchema.safeParse(form)
    if (!result.success) {
      setFieldErrors(zodErrorsToRecord(result.error))
      return
    }
    setFieldErrors({})
    invite.mutate(result.data, {
      onSuccess: (invitation) => {
        setForm(EMPTY_FORM)
        // Fragment, not query string: browsers never send it to any server or log.
        setInvitationLink(`${window.location.origin}/convite#token=${encodeURIComponent(invitation.token)}`)
      },
      onError: (error) => {
        setFieldErrors(error instanceof ApiError && error.fieldErrors ? error.fieldErrors : { _root: toUserMessage(error) })
      },
    })
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(invitationLink)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section aria-labelledby="patient-invitations-heading" className="flex flex-col gap-5 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <div>
        <h2 id="patient-invitations-heading" className="text-lg font-semibold text-slate-900">Convidar paciente</h2>
        <p className="mt-1 text-sm text-slate-600">
          O paciente recebe um link de uso único para definir a palavra-passe. A conta fica associada a esta clínica.
        </p>
      </div>

      <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
        <TextField label="Nome completo" value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} error={fieldErrors.full_name} autoComplete="off" />
        <TextField label="Email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} error={fieldErrors.email} autoComplete="off" />
        <Button type="submit" isLoading={invite.isPending}>Criar convite</Button>
      </form>
      {fieldErrors._root && <p role="alert" className="text-sm text-red-700">{fieldErrors._root}</p>}

      {invitationLink && (
        <div role="status" className="flex flex-col gap-2 rounded-md border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">
          <p className="font-medium">Convite criado. Partilhe este link apenas com o paciente — não volta a ser mostrado.</p>
          <label htmlFor="patient-invitation-link" className="sr-only">Link do convite</label>
          <input id="patient-invitation-link" readOnly value={invitationLink} className="w-full min-w-0 rounded-md border border-teal-200 bg-white px-3 py-2 font-mono text-xs" onFocus={(e) => e.target.select()} />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={copyLink}>{copied ? 'Copiado' : 'Copiar link'}</Button>
            <Button variant="secondary" onClick={() => setInvitationLink('')}>Fechar</Button>
          </div>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-slate-800">Convites pendentes</h3>
        {pending.isLoading && <LoadingSpinner label="A carregar convites…" />}
        {pending.isError && <ErrorState message={toUserMessage(pending.error)} onRetry={() => pending.refetch()} />}
        {pending.isSuccess && patientInvitations.length === 0 && (
          <p className="mt-2 text-sm text-slate-600">Não há convites de pacientes pendentes.</p>
        )}
        {actionError && <p role="alert" className="mt-2 text-sm text-red-700">{actionError}</p>}
        {patientInvitations.length > 0 && (
          <ul className="mt-2 divide-y divide-slate-100" aria-label="Convites pendentes">
            {patientInvitations.map((invitation) => {
              // Compared with the time the list was fetched, so rendering stays pure.
              const expired = new Date(invitation.expires_at).getTime() <= pending.dataUpdatedAt
              return (
                <li key={invitation.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="break-words font-medium text-slate-900">{invitation.full_name}</p>
                    <p className="break-words text-sm text-slate-600">{invitation.email}</p>
                    <p className="text-xs text-slate-600">
                      {expired ? 'Expirado em ' : 'Expira em '}
                      <time dateTime={invitation.expires_at}>{formatDateTime(invitation.expires_at)}</time>
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    isLoading={revoke.isPending && revoke.variables === invitation.id}
                    aria-label={`Revogar convite de ${invitation.full_name}`}
                    onClick={() => {
                      setActionError('')
                      revoke.mutate(invitation.id, { onError: (error) => setActionError(toUserMessage(error)) })
                    }}
                  >
                    Revogar
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
