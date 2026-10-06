import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextAreaField } from '../../components/TextAreaField'
import { TextField } from '../../components/TextField'
import {
  useCreateMedicalRecord,
  useMedicalRecordRevisions,
  useMedicalRecords,
  useUpdateMedicalRecord,
} from '../../hooks/useClinicalData'
import { formErrorsFrom, toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { medicalRecordSchema, zodErrorsToRecord } from '../../lib/validation'
import type { MedicalRecordPublic } from '../../types/api'

const EMPTY_FORM = { title: '', content: '' }
const FORM_FIELDS = ['title', 'content'] as const

export function MedicalRecordsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const records = useMedicalRecords(patientId)
  const create = useCreateMedicalRecord(patientId)
  const update = useUpdateMedicalRecord(patientId)
  const [selected, setSelected] = useState<MedicalRecordPublic | null>(null)
  const revisions = useMedicalRecordRevisions(selected?.id ?? '')
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [success, setSuccess] = useState('')
  const saving = create.isPending || update.isPending

  function resetForm() {
    setSelected(null)
    setForm(EMPTY_FORM)
    setErrors({})
  }

  function startEdit(record: MedicalRecordPublic) {
    setSelected(record)
    setForm({ title: record.title, content: record.content })
    setErrors({})
    setSuccess('')
  }

  function save(event: React.FormEvent) {
    event.preventDefault()
    if (saving) return
    setSuccess('')
    const result = medicalRecordSchema.safeParse(form)
    if (!result.success) {
      setErrors(zodErrorsToRecord(result.error))
      return
    }
    setErrors({})
    const options = {
      onSuccess: () => {
        resetForm()
        setSuccess('Registo clínico guardado.')
      },
      onError: (error: unknown) => setErrors(formErrorsFrom(error, FORM_FIELDS)),
    }
    if (selected) update.mutate({ id: selected.id, payload: result.data }, options)
    else create.mutate(result.data, options)
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="mb-4 text-lg font-medium">Histórico clínico</h2>
      {canWrite && (
        <form className="mb-6 grid gap-3 border-b border-slate-100 pb-5" onSubmit={save} noValidate>
          <TextField
            label="Título do registo"
            value={form.title}
            onChange={(event) => setForm((value) => ({ ...value, title: event.target.value }))}
            error={errors.title}
            maxLength={200}
          />
          <TextAreaField
            label="Conteúdo clínico"
            value={form.content}
            onChange={(event) => setForm((value) => ({ ...value, content: event.target.value }))}
            error={errors.content}
            maxLength={20000}
          />
          {errors._root && <FormMessage kind="error">{errors._root}</FormMessage>}
          <div className="flex items-center gap-3">
            <Button type="submit" isLoading={saving}>
              {selected ? 'Guardar nova versão' : 'Criar registo'}
            </Button>
            {selected && (
              <Button variant="secondary" disabled={saving} onClick={resetForm}>
                Cancelar edição
              </Button>
            )}
          </div>
        </form>
      )}
      {success && <FormMessage kind="success" className="mb-3">{success}</FormMessage>}
      {records.isLoading && <LoadingSpinner />}
      {records.isError && <ErrorState message={toUserMessage(records.error)} onRetry={() => records.refetch()} />}
      {records.data?.length === 0 && <EmptyState title="Sem registos clínicos" />}
      {records.data && records.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {records.data.map((record) => (
            <li key={record.id} className="py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{record.title}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{record.content}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Versão {record.version} · {formatDateTime(record.updated_at)}
                  </p>
                </div>
                {canWrite && (
                  <Button variant="secondary" disabled={saving} onClick={() => startEdit(record)}>
                    Editar
                  </Button>
                )}
              </div>
              {selected?.id === record.id && (
                <div className="mt-3 rounded-lg bg-slate-50 p-3">
                  <p className="text-sm font-medium">Revisões</p>
                  {revisions.isLoading && <LoadingSpinner />}
                  {revisions.isError && (
                    <ErrorState message={toUserMessage(revisions.error)} onRetry={() => revisions.refetch()} />
                  )}
                  {revisions.data?.map((revision) => (
                    <p key={revision.id} className="mt-1 text-xs text-slate-600">
                      Versão {revision.version} · {formatDateTime(revision.created_at)}
                    </p>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
