import { useState } from 'react'
import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'
import { TextField } from './TextField'
import { useGrantConsent, usePatientConsents, useRevokeConsent } from '../hooks/useConsents'
import { useFocusFirstInvalid } from '../hooks/useFocusFirstInvalid'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import { consentCreateSchema, zodErrorsToRecord } from '../lib/validation'
import type { ConsentType } from '../types/api'

const CONSENT_LABELS: Record<ConsentType, string> = {
  treatment: 'Tratamento',
  data_processing: 'Tratamento de dados',
  communications: 'Comunicações',
  research: 'Investigação',
}

/** Consent history; the patient grants and revokes their own consents (canManage). */
export function ConsentSection({ patientId, canManage }: { patientId: string; canManage: boolean }) {
  const consents = usePatientConsents(patientId)
  const grant = useGrantConsent(patientId)
  const revoke = useRevokeConsent(patientId)
  const [form, setForm] = useState({ consent_type: 'treatment' as ConsentType, purpose: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(errors)
  const [success, setSuccess] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setSuccess('')
    const result = consentCreateSchema.safeParse(form)
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    grant.mutate(result.data, {
      onSuccess: () => {
        setForm((current) => ({ ...current, purpose: '' }))
        setSuccess('Consentimento concedido e registado no histórico.')
      },
      onError: (error) => setErrors({ _root: toUserMessage(error) }),
    })
  }

  function confirmRevoke(consentId: string) {
    if (!window.confirm('Revogar este consentimento? O registo continuará visível no histórico.')) return
    setSuccess('')
    setErrors({})
    revoke.mutate(consentId, {
      onSuccess: () => {
        setErrors({})
        setSuccess('Consentimento revogado. O histórico foi preservado.')
      },
      onError: (error) => setErrors({ _root: toUserMessage(error) }),
    })
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="mb-5">
        <h2 className="text-lg font-medium">Consentimentos</h2>
        <p className="text-sm text-slate-500">A revogação preserva sempre o registo original no histórico.</p>
      </div>

      {canManage && <form ref={formRef} onSubmit={submit} noValidate className="mb-6 grid gap-4 border-b border-slate-200 pb-6 md:grid-cols-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="consent-type" className="text-sm font-medium text-slate-700">Tipo</label>
          <select
            id="consent-type"
            value={form.consent_type}
            onChange={(event) => {
              const parsed = consentCreateSchema.shape.consent_type.safeParse(event.target.value)
              if (parsed.success) setForm((current) => ({ ...current, consent_type: parsed.data }))
            }}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {Object.entries(CONSENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <TextField
          label="Finalidade"
          value={form.purpose}
          onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
          error={errors.purpose}
        />
        <div className="flex items-end"><Button type="submit" isLoading={grant.isPending}>Conceder</Button></div>
        {errors._root && <p role="alert" className="text-sm text-red-600 md:col-span-3">{errors._root}</p>}
        {success && <p role="status" className="text-sm text-teal-700 md:col-span-3">{success}</p>}
      </form>}

      {consents.isLoading && <LoadingSpinner label="A carregar consentimentos…" />}
      {consents.isError && <ErrorState message={toUserMessage(consents.error)} onRetry={() => consents.refetch()} />}
      {consents.data?.length === 0 && <EmptyState title="Sem consentimentos" description="Ainda não existem decisões registadas." />}
      {consents.data && consents.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {consents.data.map((consent) => (
            <li key={consent.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">{CONSENT_LABELS[consent.consent_type]}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${consent.status === 'granted' ? 'bg-teal-50 text-teal-800' : 'bg-slate-100 text-slate-700'}`}>
                    {consent.status === 'granted' ? 'Concedido' : 'Revogado'}
                  </span>
                </div>
                <p className="text-sm text-slate-600">{consent.purpose}</p>
                {consent.policy_version && <p className="mt-1 text-xs text-slate-500">Versão do texto: {consent.policy_version}</p>}
                {consent.policy_text && <details className="mt-2 text-sm text-slate-600"><summary className="cursor-pointer">Texto apresentado</summary><p className="mt-1 whitespace-pre-wrap">{consent.policy_text}</p></details>}
                <p className="mt-1 text-xs text-slate-500">Concedido em {formatDateTime(consent.granted_at)}{consent.revoked_at ? ` · Revogado em ${formatDateTime(consent.revoked_at)}` : ''}</p>
              </div>
              {canManage && consent.status === 'granted' && (
                <Button variant="secondary" disabled={revoke.isPending} onClick={() => confirmRevoke(consent.id)}>Revogar</Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
