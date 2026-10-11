import { useState } from 'react'
import { Button } from './Button'
import { ErrorState } from './ErrorState'
import { FormMessage } from './FormMessage'
import { LoadingSpinner } from './LoadingSpinner'
import { TextField } from './TextField'
import { usePatientIdentification, useRevealIdentifiers, useUpdateIdentifiers } from '../hooks/useClinicData'
import { useFocusFirstInvalid } from '../hooks/useFocusFirstInvalid'
import { ApiError } from '../lib/apiClient'
import { toUserMessage } from '../lib/errorMessages'
import { identifiersSchema, zodErrorsToRecord } from '../lib/validation'
import type { PatientIdentifiers, PatientIdentifiersUpdateRequest } from '../types/api'

const FIELDS: Array<{ key: keyof PatientIdentifiers; label: string; inputMode: 'numeric' }> = [
  { key: 'nif', label: 'NIF', inputMode: 'numeric' },
  { key: 'niss', label: 'NISS', inputMode: 'numeric' },
  { key: 'national_health_number', label: 'Nº de utente', inputMode: 'numeric' },
]

const EMPTY_FORM: Record<keyof PatientIdentifiers, string> = { nif: '', niss: '', national_health_number: '' }

/**
 * NIF, NISS and Nº de utente. The server sends them masked (last three digits);
 * "Mostrar" asks the audited reveal endpoint for the full values, kept only in this
 * component's state (never in the query cache) and dropped by "Ocultar" or on leaving.
 * "Editar" appears only when the backend says the user may change them.
 */
export function PatientIdentifiersCard({ patientId }: { patientId: string }) {
  const identification = usePatientIdentification(patientId)
  const reveal = useRevealIdentifiers(patientId)
  const update = useUpdateIdentifiers(patientId)
  const [revealed, setRevealed] = useState<PatientIdentifiers | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const formRef = useFocusFirstInvalid(errors)

  function showFull(onShown?: (values: PatientIdentifiers) => void) {
    setMessage(null)
    reveal.mutate(undefined, {
      onSuccess: (values) => {
        setRevealed(values)
        onShown?.(values)
      },
      onError: (error) => setMessage({ kind: 'error', text: toUserMessage(error) }),
    })
  }

  function startEditing() {
    // Editing needs the current values: they are revealed (and audited) first.
    const begin = (values: PatientIdentifiers) => {
      setForm({ nif: values.nif ?? '', niss: values.niss ?? '', national_health_number: values.national_health_number ?? '' })
      setErrors({})
      setEditing(true)
    }
    if (revealed) begin(revealed)
    else showFull(begin)
  }

  function save(event: React.FormEvent) {
    event.preventDefault()
    setMessage(null)
    const parsed = identifiersSchema.safeParse(form)
    if (!parsed.success) {
      setErrors(zodErrorsToRecord(parsed.error))
      return
    }
    const payload: PatientIdentifiersUpdateRequest = {}
    for (const { key } of FIELDS) {
      const next = parsed.data[key] || null
      if (next !== (revealed?.[key] ?? null)) payload[key] = next
    }
    if (Object.keys(payload).length === 0) {
      setEditing(false)
      return
    }
    update.mutate(payload, {
      onSuccess: () => {
        setEditing(false)
        setRevealed(null)
        setErrors({})
        setMessage({ kind: 'success', text: 'Dados identificativos atualizados.' })
      },
      onError: (error) => {
        if (error instanceof ApiError && error.fieldErrors) setErrors(error.fieldErrors)
        else setErrors({ _root: toUserMessage(error) })
      },
    })
  }

  const data = identification.data
  return (
    <section aria-labelledby="identifiers-title" className="rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
        <h2 id="identifiers-title" className="text-base font-semibold text-slate-900">Dados identificativos</h2>
        {data && !editing && (
          <div className="flex flex-wrap gap-2">
            {revealed ? (
              <Button variant="secondary" aria-label="Ocultar dados identificativos" onClick={() => setRevealed(null)}>Ocultar</Button>
            ) : (
              <Button variant="secondary" aria-label="Mostrar dados identificativos" isLoading={reveal.isPending} onClick={() => showFull()}>Mostrar</Button>
            )}
            {data.can_edit && (
              <Button variant="secondary" aria-label="Editar dados identificativos" disabled={reveal.isPending} onClick={startEditing}>Editar</Button>
            )}
          </div>
        )}
      </div>
      {identification.isLoading && <div className="px-5 py-3"><LoadingSpinner label="A carregar dados identificativos…" /></div>}
      {identification.isError && (
        <div className="px-5 py-3"><ErrorState message={toUserMessage(identification.error)} onRetry={() => identification.refetch()} /></div>
      )}
      {data && !editing && (
        <dl className="divide-y divide-slate-100">
          {FIELDS.map(({ key, label }) => {
            const value = (revealed ?? data.identifiers)[key]
            return (
              <div key={key} className="flex justify-between gap-3 px-5 py-3">
                <dt className="text-sm text-slate-500">{label}</dt>
                <dd className="font-mono text-sm font-medium text-slate-900">
                  {value ?? '—'}
                  {value && !revealed && <span className="sr-only"> (só os últimos 3 dígitos)</span>}
                </dd>
              </div>
            )
          })}
        </dl>
      )}
      {editing && (
        <form ref={formRef} noValidate onSubmit={save} aria-label="Editar dados identificativos" className="grid gap-3 px-5 py-4 sm:grid-cols-3">
          {FIELDS.map(({ key, label, inputMode }) => (
            <TextField
              key={key}
              label={label}
              inputMode={inputMode}
              autoComplete="off"
              value={form[key]}
              onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
              error={errors[key]}
              maxLength={15}
            />
          ))}
          {errors._root && <FormMessage kind="error" className="sm:col-span-3">{errors._root}</FormMessage>}
          <div className="flex flex-wrap gap-2 sm:col-span-3">
            <Button type="submit" isLoading={update.isPending}>Guardar</Button>
            <Button variant="secondary" disabled={update.isPending} onClick={() => { setEditing(false); setErrors({}) }}>Cancelar</Button>
          </div>
        </form>
      )}
      {message && <FormMessage kind={message.kind} className="px-5 pb-4">{message.text}</FormMessage>}
      <div className="pb-1" />
    </section>
  )
}
