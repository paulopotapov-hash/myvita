import { useMemo, useState } from 'react'
import { Button } from '../Button'
import { FormMessage } from '../FormMessage'
import { SelectField } from '../SelectField'
import { TextAreaField } from '../TextAreaField'
import { TextField } from '../TextField'
import { PartialDateField } from './PartialDateField'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'
import { CATEGORY_FIELDS, CONDITION_STATUS_LABELS, SEVERITY_LABELS } from '../../lib/clinicalHistoryLabels'
import type { AllergySeverity, ClinicalHistoryFields, ConditionStatus, HistoryCategory } from '../../types/api'

type FormValues = Record<keyof ClinicalHistoryFields, string>

const EMPTY: FormValues = {
  name: '', condition_status: '', onset: '', resolved: '', occurred: '', location: '', reaction: '', severity: '', note_text: '',
}

const REQUIRED: Record<HistoryCategory, Array<keyof ClinicalHistoryFields>> = {
  condition: ['name', 'condition_status'],
  procedure: ['name'],
  allergy: ['name', 'severity'],
  immunization: ['name'],
  note: ['note_text'],
}
const NAME_LABELS: Record<HistoryCategory, string> = {
  condition: 'Doença ou problema',
  procedure: 'Cirurgia ou procedimento',
  allergy: 'Substância',
  immunization: 'Vacina',
  note: 'Nota',
}
const DATE_PATTERN = /^\d{4}(-\d{2}(-\d{2})?)?$/

interface Props {
  category: HistoryCategory
  initial?: Partial<ClinicalHistoryFields>
  submitLabel: string
  isPending: boolean
  /** Field errors from the backend (keys are field names), or `_root`. */
  serverErrors?: Record<string, string>
  onSubmit: (values: Partial<ClinicalHistoryFields>) => void
  onCancel: () => void
}

export function HistoryEntryForm({ category, initial, submitLabel, isPending, serverErrors, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState<FormValues>(() => {
    const start = { ...EMPTY }
    for (const [key, value] of Object.entries(initial ?? {})) start[key as keyof FormValues] = value ?? ''
    return start
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  // Stable until the next submit or server answer, so focus moves only after a failed submit.
  const shown = useMemo(() => ({ ...serverErrors, ...errors }), [serverErrors, errors])
  const formRef = useFocusFirstInvalid(shown)
  const fields = CATEGORY_FIELDS[category]
  const set = (key: keyof FormValues) => (value: string) => setValues((current) => ({ ...current, [key]: value }))

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const next: Record<string, string> = {}
    for (const key of REQUIRED[category]) if (!values[key].trim()) next[key] = 'Campo obrigatório.'
    for (const key of ['onset', 'resolved', 'occurred'] as const) {
      // The resolution date only counts (and is only shown) for a resolved condition.
      if (key === 'resolved' && values.condition_status !== 'resolved') continue
      if (fields.includes(key) && values[key] && !DATE_PATTERN.test(values[key])) next[key] = 'Data incompleta ou inválida.'
    }
    if (Object.keys(next).length > 0) {
      setErrors(next)
      return
    }
    setErrors({})
    const payload: Partial<ClinicalHistoryFields> = {}
    for (const key of fields) {
      const value = values[key].trim()
      ;(payload as Record<string, string | null>)[key] = value || null
    }
    if (category === 'condition' && values.condition_status !== 'resolved') payload.resolved = null
    onSubmit(payload)
  }

  return (
    <form ref={formRef} noValidate onSubmit={submit} aria-label={submitLabel} className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2">
      {fields.includes('name') && (
        <TextField label={NAME_LABELS[category]} required value={values.name} maxLength={200} onChange={(event) => set('name')(event.target.value)} error={shown.name || undefined} />
      )}
      {fields.includes('condition_status') && (
        <SelectField label="Estado" required value={values.condition_status} onChange={(event) => set('condition_status')(event.target.value)} error={shown.condition_status || undefined}>
          <option value="">Escolhe…</option>
          {(Object.keys(CONDITION_STATUS_LABELS) as ConditionStatus[]).map((key) => <option key={key} value={key}>{CONDITION_STATUS_LABELS[key]}</option>)}
        </SelectField>
      )}
      {fields.includes('onset') && <PartialDateField label="Início" value={values.onset} onChange={set('onset')} error={shown.onset || undefined} />}
      {fields.includes('resolved') && values.condition_status === 'resolved' && (
        <PartialDateField label="Resolução" value={values.resolved} onChange={set('resolved')} error={shown.resolved || undefined} />
      )}
      {fields.includes('occurred') && <PartialDateField label="Data" value={values.occurred} onChange={set('occurred')} error={shown.occurred || undefined} />}
      {fields.includes('location') && (
        <TextField label="Local (opcional)" value={values.location} maxLength={200} onChange={(event) => set('location')(event.target.value)} error={shown.location || undefined} />
      )}
      {fields.includes('reaction') && (
        <TextField label="Reação (opcional)" value={values.reaction} maxLength={500} onChange={(event) => set('reaction')(event.target.value)} error={shown.reaction || undefined} />
      )}
      {fields.includes('severity') && (
        <SelectField label="Gravidade" required value={values.severity} onChange={(event) => set('severity')(event.target.value)} error={shown.severity || undefined}>
          <option value="">Escolhe…</option>
          {(Object.keys(SEVERITY_LABELS) as AllergySeverity[]).map((key) => <option key={key} value={key}>{SEVERITY_LABELS[key]}</option>)}
        </SelectField>
      )}
      {fields.includes('note_text') && (
        <div className="sm:col-span-2">
          <TextAreaField label="Nota" required value={values.note_text} maxLength={5000} onChange={(event) => set('note_text')(event.target.value)} error={shown.note_text || undefined} />
        </div>
      )}
      {shown._root && <FormMessage kind="error" className="sm:col-span-2">{shown._root}</FormMessage>}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button type="submit" isLoading={isPending}>{submitLabel}</Button>
        <Button variant="secondary" disabled={isPending} onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  )
}
