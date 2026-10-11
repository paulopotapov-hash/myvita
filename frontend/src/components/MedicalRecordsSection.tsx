import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../lib/apiClient'
import { Button } from './Button'
import { ConfirmDialog } from './ConfirmDialog'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'
import { TextField } from './TextField'
import { useChangeRecordVisibility, useCreateMedicalRecord, useMedicalRecord, useMedicalRecords, useMedicalRecordRevisions, useUpdateMedicalRecord } from '../hooks/useClinicalData'
import { useFocusFirstInvalid } from '../hooks/useFocusFirstInvalid'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import type { MedicalRecordPublic, MedicalRecordView, MedicalRecordVisibility } from '../types/api'

const RECORD_REQUIRED = 'Preenche o título e o conteúdo clínico.'
// 403 and 404 look the same to the user: the backend hides records the caller may not see.
const RECORD_UNAVAILABLE = 'Este registo não está disponível. Pode ter deixado de estar partilhado contigo.'
const SHARE_STALE = 'O registo foi alterado desde que o abriste. Revê a versão atual antes de o partilhar.'

const VISIBILITY_LABELS: Record<MedicalRecordVisibility, { badge: string; revision: string; tone: string }> = {
  internal: { badge: 'Nota interna', revision: 'Interno', tone: 'bg-slate-100 text-slate-700' },
  shared: { badge: 'Partilhado com o paciente', revision: 'Partilhado', tone: 'bg-teal-50 text-teal-800' },
  legacy_shared: { badge: 'Visível ao paciente (registo anterior à partilha explícita)', revision: 'Visível (anterior)', tone: 'bg-amber-50 text-amber-800' },
}

type VisibilityChange = { record: MedicalRecordPublic; share: boolean }

/** Medical records: the care team writes and shares; the patient reads shared records (P2.5). */
export function MedicalRecordsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const records = useMedicalRecords(patientId)
  const create = useCreateMedicalRecord(patientId)
  const update = useUpdateMedicalRecord(patientId)
  const visibility = useChangeRecordVisibility(patientId)
  const [selected, setSelected] = useState<MedicalRecordPublic | null>(null)
  const revisions = useMedicalRecordRevisions(selected?.id ?? '')
  const [form, setForm] = useState({ title: '', content: '', share_with_patient: false })
  const [message, setMessage] = useState('')
  const [invalid, setInvalid] = useState<Record<string, string>>({})
  const formRef = useFocusFirstInvalid(invalid)
  const [leaveConfirmation, setLeaveConfirmation] = useState<(() => void) | null>(null)
  const [visibilityChange, setVisibilityChange] = useState<VisibilityChange | null>(null)
  const [visibilityMessage, setVisibilityMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  // Deep link from a "record shared" notification: ?record=<id>. Access is re-checked by the backend.
  const [searchParams] = useSearchParams()
  const linkedId = searchParams.get('record')
  const linkedOnList = Boolean(linkedId && records.data?.some((item) => item.id === linkedId))
  const linkedRecord = useMedicalRecord(linkedId && records.data && !linkedOnList ? linkedId : null)
  const formDirty = Boolean(form.title || form.content)
  const startEditing = (record: MedicalRecordPublic) => { setSelected(record); setForm({ title: record.title, content: record.content, share_with_patient: false }); setMessage('') }
  const saving = create.isPending || update.isPending

  function leaveEditor() {
    setSelected(null)
    setForm({ title: '', content: '', share_with_patient: false })
  }

  function save(event: React.FormEvent) {
    event.preventDefault()
    setMessage('')
    const missing: Record<string, string> = {}
    if (!form.title.trim()) missing.title = RECORD_REQUIRED
    if (!form.content.trim()) missing.content = RECORD_REQUIRED
    setInvalid(missing)
    if (Object.keys(missing).length > 0) {
      setMessage(RECORD_REQUIRED)
      return
    }
    const options = {
      onSuccess: () => {
        leaveEditor()
        setMessage('Registo clínico guardado.')
      },
      onError: (error: unknown) => setMessage(error instanceof ApiError && error.status === 409
        ? error.detail ?? 'Este registo foi alterado por outra pessoa. Atualiza a ficha e volta a tentar.'
        : toUserMessage(error)),
    }
    // An edit never changes visibility: sharing is a separate, explicit action.
    if (selected) update.mutate({ id: selected.id, payload: { title: form.title, content: form.content, expected_version: selected.version } }, options)
    else create.mutate(form, options)
  }

  function confirmVisibilityChange() {
    if (!visibilityChange) return
    const { record, share } = visibilityChange
    visibility.mutate({ id: record.id, share, expectedVersion: record.version }, {
      onSuccess: () => {
        setVisibilityChange(null)
        if (selected?.id === record.id) leaveEditor()
        setVisibilityMessage({ tone: 'ok', text: share ? 'Registo partilhado com o paciente.' : 'O paciente deixou de ter acesso a este registo.' })
      },
      onError: (error) => {
        setVisibilityChange(null)
        setVisibilityMessage({ tone: 'error', text: error instanceof ApiError && error.status === 409 ? SHARE_STALE : toUserMessage(error) })
      },
    })
  }

  const selectedVisibleToPatient = selected !== null && selected.visibility !== 'internal'

  return (
    <section aria-labelledby="records-title" className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 id="records-title" className="mb-4 text-lg font-medium">Registos clínicos</h2>
      {canWrite && (
        <form ref={formRef} className="mb-6 grid gap-3 border-b border-slate-100 pb-5" onSubmit={save} noValidate>
          <TextField label="Título do registo" value={form.title} onChange={(event) => setForm((value) => ({ ...value, title: event.target.value }))} aria-invalid={Boolean(invalid.title)} aria-describedby={invalid.title ? 'record-form-message' : undefined} />
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">Conteúdo clínico
            <textarea className="min-h-28 rounded-md border border-slate-300 px-3 py-2 font-normal" aria-invalid={Boolean(invalid.content)} aria-describedby={invalid.content ? 'record-form-message' : undefined} value={form.content} onChange={(event) => setForm((value) => ({ ...value, content: event.target.value }))} maxLength={20000} />
          </label>
          {selected ? (
            selectedVisibleToPatient && (
              <p role="note" className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
                Este registo está visível para o paciente: as alterações que guardares ficam visíveis de imediato. Para o tornar interno, usa «Deixar de partilhar».
              </p>
            )
          ) : (
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300" checked={form.share_with_patient} onChange={(event) => setForm((value) => ({ ...value, share_with_patient: event.target.checked }))} />
              <span>Partilhar com o paciente<span className="block text-xs text-slate-500">Sem esta opção, o registo é uma nota interna da equipa clínica e o paciente não o vê. Ao partilhar, o paciente recebe uma notificação genérica, sem o conteúdo.</span></span>
            </label>
          )}
          <div className="flex flex-wrap items-center gap-3"><Button type="submit" isLoading={saving}>{selected ? 'Guardar alterações' : 'Criar registo'}</Button>{selected && <Button variant="secondary" disabled={saving} onClick={() => { if (formDirty) setLeaveConfirmation(() => leaveEditor); else leaveEditor() }}>Cancelar edição</Button>}</div>
          {message && <p id="record-form-message" role={message.includes('guardado') ? 'status' : 'alert'} className={`text-sm ${message.includes('guardado') ? 'text-teal-700' : 'text-red-700'}`}>{message}</p>}
        </form>
      )}
      {visibilityMessage && (
        <p role={visibilityMessage.tone === 'ok' ? 'status' : 'alert'} className={`mb-3 text-sm ${visibilityMessage.tone === 'ok' ? 'text-teal-700' : 'text-red-700'}`}>{visibilityMessage.text}</p>
      )}
      {linkedId && !linkedOnList && linkedRecord.data && (
        <ul className="mb-4" aria-label="Registo aberto a partir da notificação">
          <RecordItem record={linkedRecord.data} canWrite={false} linked selected={false} onEdit={() => undefined} onVisibility={() => undefined} revisions={null} />
        </ul>
      )}
      {linkedId && !linkedOnList && linkedRecord.isError && (
        <p role="alert" className="mb-3 text-sm text-red-700">{RECORD_UNAVAILABLE}</p>
      )}
      {records.isLoading && <LoadingSpinner />}
      {records.isError && <ErrorState message={toUserMessage(records.error)} onRetry={() => records.refetch()} />}
      {records.data?.length === 0 && <EmptyState title="Sem registos clínicos" description={canWrite ? undefined : 'A tua equipa clínica ainda não partilhou registos contigo.'} />}
      {records.data && records.data.length > 0 && <ul className="divide-y divide-slate-100">{records.data.map((record) => <RecordItem key={record.id} record={record} canWrite={canWrite} linked={record.id === linkedId} selected={selected?.id === record.id} onEdit={(staffRecord) => { if (formDirty) { setLeaveConfirmation(() => () => startEditing(staffRecord)); return } startEditing(staffRecord) }} onVisibility={(staffRecord, share) => { setVisibilityMessage(null); setVisibilityChange({ record: staffRecord, share }) }} revisions={selected?.id === record.id ? revisions : null} />)}</ul>}
      {leaveConfirmation && <ConfirmDialog title="Descartar alterações" description="As alterações ainda não guardadas serão perdidas." confirmLabel="Descartar" onCancel={() => setLeaveConfirmation(null)} onConfirm={() => { const action = leaveConfirmation; setLeaveConfirmation(null); action() }} />}
      {visibilityChange && (
        <ConfirmDialog
          title={visibilityChange.share ? 'Partilhar com o paciente' : 'Deixar de partilhar'}
          description={visibilityChange.share
            ? `O paciente passa a ver este registo tal como está agora (versão ${visibilityChange.record.version}). ${visibilityChange.record.visibility === 'internal' ? 'Recebe uma notificação genérica, sem o título nem o conteúdo.' : 'Já o via; fica registada a tua decisão explícita.'} Confirma que reviste o conteúdo.`
            : 'O paciente deixa de ver este registo de imediato, mesmo a partir de notificações antigas. O registo e o seu histórico mantêm-se para a equipa clínica.'}
          confirmLabel={visibilityChange.share ? 'Partilhar' : 'Deixar de partilhar'}
          isPending={visibility.isPending}
          onCancel={() => setVisibilityChange(null)}
          onConfirm={confirmVisibilityChange}
        />
      )}
    </section>
  )
}

function RecordItem({ record, canWrite, linked, selected, onEdit, onVisibility, revisions }: {
  record: MedicalRecordView
  canWrite: boolean
  linked: boolean
  selected: boolean
  onEdit: (record: MedicalRecordPublic) => void
  onVisibility: (record: MedicalRecordPublic, share: boolean) => void
  revisions: ReturnType<typeof useMedicalRecordRevisions> | null
}) {
  return (
    <li className={`py-4 ${linked ? '-mx-3 rounded-lg bg-teal-50 px-3 ring-2 ring-teal-600' : ''}`} aria-current={linked ? 'true' : undefined}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{record.title}</p>
            {record.view === 'staff' && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VISIBILITY_LABELS[record.visibility].tone}`}>
                {VISIBILITY_LABELS[record.visibility].badge}
              </span>
            )}
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{record.content}</p>
          <p className="mt-1 text-xs text-slate-500">
            Autor {record.author_name} · Criado {formatDateTime(record.created_at)}
            {record.view === 'staff' ? ` · Versão ${record.version}` : ''} · Atualizado {formatDateTime(record.updated_at)}
          </p>
          {record.view === 'staff' && record.visibility_changed_at && (
            <p className="mt-1 text-xs text-slate-500">
              {record.visibility === 'shared' ? 'Partilhado' : 'Deixou de ser partilhado'} por {record.visibility_changed_by_name} em {formatDateTime(record.visibility_changed_at)}
            </p>
          )}
        </div>
        {canWrite && record.view === 'staff' && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => onEdit(record)}>Editar</Button>
            {record.visibility !== 'shared' && <Button variant="secondary" onClick={() => onVisibility(record, true)}>{record.visibility === 'legacy_shared' ? 'Confirmar partilha' : 'Partilhar com o paciente'}</Button>}
            {record.visibility !== 'internal' && <Button variant="secondary" onClick={() => onVisibility(record, false)}>Deixar de partilhar</Button>}
          </div>
        )}
      </div>
      {selected && revisions && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3">
          <p className="text-sm font-medium">Revisões</p>
          {revisions.isLoading && <LoadingSpinner />}
          {revisions.isError && <ErrorState message={toUserMessage(revisions.error)} onRetry={() => revisions.refetch()} />}
          {revisions.data?.length === 0 && <p className="mt-1 text-sm text-slate-500">Sem revisões anteriores.</p>}
          {revisions.data?.map((revision) => <p key={revision.id} className="mt-1 text-xs text-slate-600">Autor {revision.editor_name} · Versão {revision.version} · {VISIBILITY_LABELS[revision.visibility].revision} · {formatDateTime(revision.created_at)}</p>)}
        </div>
      )}
    </li>
  )
}
