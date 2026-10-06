import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextAreaField } from '../../components/TextAreaField'
import { TextField } from '../../components/TextField'
import {
  useCreateMedication,
  useDeactivateMedication,
  useMedications,
  useUpdateMedication,
} from '../../hooks/useClinicalData'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { formatDate } from '../../lib/formatDate'
import {
  EMPTY_MEDICATION_FORM,
  medicationToForm,
  toCreatePayload,
  toUpdatePayload,
} from '../../lib/medicationPayloads'
import { medicationFormSchema, zodErrorsToRecord } from '../../lib/validation'
import type { MedicationFormValues } from '../../lib/validation'
import type { MedicationPublic, MedicationStatus } from '../../types/api'
import { useFocusFirstInvalid } from '../../hooks/useFocusFirstInvalid'

const FORM_FIELDS = ['name', 'dosage', 'route', 'frequency', 'instructions', 'start_date', 'end_date'] as const

const STATUS_LABELS: Record<MedicationStatus, string> = {
  active: 'Ativa',
  completed: 'Concluída',
  discontinued: 'Descontinuada',
}

const FINISH_COPY = {
  completed: {
    confirm: 'Marcar esta medicação como concluída? Deixa de poder ser editada.',
    success: 'Medicação concluída.',
  },
  discontinued: {
    confirm: 'Descontinuar esta medicação? Deixa de poder ser editada.',
    success: 'Medicação descontinuada.',
  },
} as const

export function MedicationsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const medications = useMedications(patientId)
  const create = useCreateMedication(patientId)
  const update = useUpdateMedication(patientId)
  const deactivate = useDeactivateMedication(patientId)
  const [editing, setEditing] = useState<MedicationPublic | null>(null)
  const [form, setForm] = useState<MedicationFormValues>(EMPTY_MEDICATION_FORM)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(errors)
  const [success, setSuccess] = useState('')

  const saving = create.isPending || (editing !== null && update.isPending)
  const busy = create.isPending || update.isPending || deactivate.isPending

  function setField(key: keyof MedicationFormValues, value: string) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function resetForm() {
    setEditing(null)
    setForm(EMPTY_MEDICATION_FORM)
    setErrors({})
  }

  function startEdit(medication: MedicationPublic) {
    setEditing(medication)
    setForm(medicationToForm(medication))
    setErrors({})
    setSuccess('')
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    setSuccess('')
    const result = medicationFormSchema.safeParse(form)
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    const onError = (error: unknown) => setErrors(formErrorsFrom(error, FORM_FIELDS))

    if (editing) {
      const payload = toUpdatePayload(result.data, editing)
      if (Object.keys(payload).length === 0) {
        setErrors({ _root: 'Não há alterações para guardar.' })
        return
      }
      update.mutate(
        { id: editing.id, payload },
        {
          onSuccess: () => {
            resetForm()
            setSuccess('Medicação atualizada.')
          },
          onError,
        },
      )
      return
    }
    create.mutate(toCreatePayload(result.data), {
      onSuccess: () => {
        resetForm()
        setSuccess('Medicação adicionada.')
      },
      onError,
    })
  }

  function finish(medication: MedicationPublic, outcome: keyof typeof FINISH_COPY) {
    if (busy) return
    if (!window.confirm(`${FINISH_COPY[outcome].confirm} (${medication.name})`)) return
    setSuccess('')
    setErrors({})
    const options = {
      onSuccess: () => {
        if (editing?.id === medication.id) resetForm()
        setSuccess(FINISH_COPY[outcome].success)
      },
      onError: (error: unknown) => setErrors({ _root: toUserMessage(error) }),
    }
    if (outcome === 'completed') update.mutate({ id: medication.id, payload: { status: 'completed' } }, options)
    else deactivate.mutate(medication.id, options)
  }

  const items = medications.data?.items ?? []
  const total = medications.data?.total ?? 0

  return (
    <section aria-labelledby="medications-title" className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 id="medications-title" className="mb-4 text-lg font-medium">Medicação</h2>
      {canWrite && (
        <form ref={formRef} onSubmit={submit} noValidate className="mb-6 grid gap-3 border-b border-slate-100 pb-5 sm:grid-cols-2">
          <h3 className="text-sm font-medium text-slate-700 sm:col-span-2">
            {editing ? `Editar ${editing.name}` : 'Nova medicação'}
          </h3>
          <TextField label="Medicamento" required value={form.name} onChange={(event) => setField('name', event.target.value)} error={errors.name} maxLength={200} />
          <TextField label="Dosagem" required value={form.dosage} onChange={(event) => setField('dosage', event.target.value)} error={errors.dosage} maxLength={200} />
          <TextField label="Via de administração (opcional)" value={form.route} onChange={(event) => setField('route', event.target.value)} error={errors.route} maxLength={100} />
          <TextField label="Frequência (opcional)" value={form.frequency} onChange={(event) => setField('frequency', event.target.value)} error={errors.frequency} maxLength={100} />
          <TextField label="Data de início" required type="date" value={form.start_date} onChange={(event) => setField('start_date', event.target.value)} error={errors.start_date} />
          <TextField label="Data de fim (opcional)" type="date" value={form.end_date} onChange={(event) => setField('end_date', event.target.value)} error={errors.end_date} />
          <div className="sm:col-span-2">
            <TextAreaField label="Instruções (opcional)" value={form.instructions} onChange={(event) => setField('instructions', event.target.value)} error={errors.instructions} maxLength={2000} />
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button type="submit" isLoading={saving} disabled={busy}>
              {editing ? 'Guardar alterações' : 'Adicionar medicação'}
            </Button>
            {editing && (
              <Button variant="secondary" disabled={busy} onClick={resetForm}>
                Cancelar edição
              </Button>
            )}
          </div>
        </form>
      )}
      {errors._root && <FormMessage kind="error" className="mb-3">{errors._root}</FormMessage>}
      {success && <FormMessage kind="success" className="mb-3">{success}</FormMessage>}

      {medications.isLoading && <LoadingSpinner />}
      {medications.isError && <ErrorState message={toUserMessage(medications.error)} onRetry={() => medications.refetch()} />}
      {medications.data && items.length === 0 && (
        <EmptyState title="Sem medicação" description={canWrite ? 'Usa o formulário acima para adicionar a primeira medicação.' : undefined} />
      )}
      {items.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {items.map((medication) => (
            <li key={medication.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p id={`medication-${medication.id}`} className="font-medium">{medication.name} · {medication.dosage}</p>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{STATUS_LABELS[medication.status]}</span>
                </div>
                <p className="text-sm text-slate-500">
                  Início {formatDate(medication.start_date)}
                  {medication.end_date && ` · Fim ${formatDate(medication.end_date)}`}
                  {medication.route && ` · Via ${medication.route}`}
                  {medication.frequency && ` · ${medication.frequency}`}
                </p>
                {medication.instructions && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{medication.instructions}</p>}
              </div>
              {canWrite && medication.status === 'active' && (
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" aria-describedby={`medication-${medication.id}`} disabled={busy} onClick={() => startEdit(medication)}>Editar</Button>
                  <Button variant="secondary" aria-describedby={`medication-${medication.id}`} disabled={busy} isLoading={update.isPending && update.variables?.id === medication.id && update.variables.payload.status === 'completed'} onClick={() => finish(medication, 'completed')}>Concluir</Button>
                  <Button variant="secondary" aria-describedby={`medication-${medication.id}`} disabled={busy} isLoading={deactivate.isPending && deactivate.variables === medication.id} onClick={() => finish(medication, 'discontinued')}>Descontinuar</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {total > items.length && (
        <p className="mt-3 text-sm text-slate-500">A mostrar as {items.length} medicações mais recentes de {total}.</p>
      )}
    </section>
  )
}
