import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from './Button'
import { ConfirmDialog } from './ConfirmDialog'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'
import { SelectField } from './SelectField'
import { TextAreaField } from './TextAreaField'
import { TextField } from './TextField'
import { usePatientDocuments } from '../hooks/useDocuments'
import {
  useClinicalResult,
  useClinicalResults,
  useCorrectClinicalResult,
  useCreateClinicalResult,
  useReleaseClinicalResult,
  useUpdateClinicalResult,
} from '../hooks/useClinicalResults'
import { ApiError } from '../lib/apiClient'
import { toUserMessage } from '../lib/errorMessages'
import { formatDate, formatDateTime } from '../lib/formatDate'
import {
  CORRECTION_REASON_MAX_LENGTH,
  RESULT_REFERENCE_MAX_LENGTH,
  RESULT_SUMMARY_MAX_LENGTH,
  RESULT_TITLE_MAX_LENGTH,
  RESULT_UNIT_MAX_LENGTH,
  RESULT_VALUE_MAX_LENGTH,
} from '../services/clinicalResults'
import { EMPTY_RESULT_FORM, RESULT_CATEGORY_LABELS, todayIso, validateResultForm, type ResultFormState } from '../lib/clinicalResultForm'
import type {
  ClinicalResultCategory,
  ClinicalResultCorrectionRequest,
  ClinicalResultCreateRequest,
  ClinicalResultPublic,
  ClinicalResultStaffView,
} from '../types/api'

const PAGE_SIZE = 20

// 403 and 404 look the same to the user: the backend hides results the caller may not see.
const RESULT_ACCESS_MESSAGE = 'Não tens acesso a este resultado ou ele já não está disponível.'

function resultErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 403 || error.status === 404)) return RESULT_ACCESS_MESSAGE
  if (error instanceof ApiError && (error.status === 409 || error.status === 422) && error.detail) return error.detail
  return toUserMessage(error)
}

function toCreatePayload(form: ResultFormState): ClinicalResultCreateRequest {
  const optional = (value: string) => (value.trim() ? value.trim() : undefined)
  return {
    category: form.category,
    title: form.title.trim(),
    value: optional(form.value),
    unit: optional(form.unit),
    reference_range: optional(form.reference_range),
    summary: optional(form.summary),
    result_date: form.result_date,
    document_id: form.document_id || undefined,
    release: form.release,
  }
}

/** Editing a draft keeps its values; correcting a released result starts from what was released. */
function formFromResult(result: ClinicalResultStaffView): ResultFormState {
  return {
    category: result.category,
    title: result.title,
    value: result.value ?? '',
    unit: result.unit ?? '',
    reference_range: result.reference_range ?? '',
    summary: result.summary ?? '',
    result_date: result.result_date,
    document_id: result.document_id ?? '',
    release: false,
    correction_reason: result.correction_reason ?? '',
  }
}

type FormMode = { kind: 'edit'; result: ClinicalResultStaffView } | { kind: 'correct'; original: ClinicalResultStaffView }

interface Props {
  patientId: string
  /** Doctor/nurse on the care team; mirrors backend `clinical_staff` + EDIT_RESULTS. */
  canManage: boolean
  /** Patient area: linked documents open in the patient's own documents page. */
  patientArea?: boolean
}

export function ClinicalResultsSection({ patientId, canManage, patientArea = false }: Props) {
  const [page, setPage] = useState(1)
  const results = useClinicalResults(patientId, page, PAGE_SIZE)
  const [searchParams] = useSearchParams()
  // Deep link from a "Novo resultado disponível" notification: ?result=<id>.
  const linkedId = searchParams.get('result')
  const [openId, setOpenId] = useState<string | null>(linkedId)
  const linkedOnPage = Boolean(linkedId && results.data?.items.some((item) => item.id === linkedId))
  // The linked result may be on another page: load it on its own (access re-checked by the backend).
  const linkedResult = useClinicalResult(linkedId && results.data && !linkedOnPage ? linkedId : null)
  const linkedRow = useRef<HTMLLIElement>(null)
  const [formMode, setFormMode] = useState<FormMode | null>(null)
  const [releasing, setReleasing] = useState<ClinicalResultStaffView | null>(null)
  const [actionMessage, setActionMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const release = useReleaseClinicalResult(patientId)

  useEffect(() => {
    if (!linkedOnPage || !linkedRow.current) return
    linkedRow.current.focus()
    linkedRow.current.scrollIntoView?.({ block: 'center' })
  }, [linkedOnPage])

  const total = results.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function confirmRelease() {
    if (!releasing) return
    const target = releasing
    release.mutate(target.id, {
      onSuccess: () => {
        setReleasing(null)
        setActionMessage({ tone: 'ok', text: 'Resultado disponibilizado ao paciente.' })
      },
      onError: (error) => {
        setReleasing(null)
        setActionMessage({ tone: 'error', text: resultErrorMessage(error) })
      },
    })
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6" aria-labelledby="results-heading">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="results-heading" className="text-lg font-medium">Resultados</h2>
          <p className="text-sm text-slate-500">
            {canManage
              ? 'Os rascunhos só ficam visíveis para o paciente depois de disponibilizados.'
              : 'Resultados disponibilizados pela tua equipa clínica.'}
          </p>
        </div>
        {results.data && <p className="text-sm text-slate-500">{total} {total === 1 ? 'resultado' : 'resultados'}</p>}
      </div>

      {canManage && (
        <ResultForm
          key={formMode ? `${formMode.kind}-${formMode.kind === 'edit' ? formMode.result.id : formMode.original.id}` : 'new'}
          patientId={patientId}
          mode={formMode}
          onDone={(text) => { setFormMode(null); setActionMessage(text ? { tone: 'ok', text } : null) }}
        />
      )}

      {actionMessage && (
        <p role={actionMessage.tone === 'ok' ? 'status' : 'alert'} className={`mb-3 text-sm ${actionMessage.tone === 'ok' ? 'text-teal-700' : 'text-red-700'}`}>
          {actionMessage.text}
        </p>
      )}

      {linkedId && !linkedOnPage && linkedResult.data && (
        <div className="mb-4 rounded-lg bg-teal-50 p-4 ring-2 ring-teal-600">
          <ResultSummary result={linkedResult.data} />
          <ResultDetail result={linkedResult.data} patientArea={patientArea} />
        </div>
      )}
      {linkedId && !linkedOnPage && linkedResult.isError && (
        <p role="alert" className="mb-3 text-sm text-red-700">{resultErrorMessage(linkedResult.error)}</p>
      )}

      {results.isLoading && <LoadingSpinner label="A carregar resultados…" />}
      {results.isError && <ErrorState message={toUserMessage(results.error)} onRetry={() => results.refetch()} />}
      {results.data?.items.length === 0 && (
        <EmptyState
          title="Sem resultados"
          description={canManage ? 'Ainda não foram registados resultados para este paciente.' : 'Ainda não existem resultados disponíveis na tua ficha.'}
        />
      )}

      {results.data && results.data.items.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Lista de resultados">
          {results.data.items.map((result) => {
            const linked = result.id === linkedId
            const open = openId === result.id
            return (
              <li
                key={result.id}
                ref={linked ? linkedRow : undefined}
                tabIndex={linked ? -1 : undefined}
                aria-current={linked ? 'true' : undefined}
                className={`py-4 outline-none ${linked ? '-mx-3 rounded-lg bg-teal-50 px-3 ring-2 ring-teal-600' : ''}`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <ResultSummary result={result} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" aria-expanded={open} aria-controls={`result-detail-${result.id}`} onClick={() => setOpenId(open ? null : result.id)}>
                      {open ? 'Fechar' : 'Ver detalhe'}
                    </Button>
                    {canManage && result.view === 'staff' && result.status === 'draft' && (
                      <>
                        <Button variant="secondary" onClick={() => { setActionMessage(null); setFormMode({ kind: 'edit', result }) }}>Editar</Button>
                        <Button onClick={() => { setActionMessage(null); setReleasing(result) }}>Disponibilizar</Button>
                      </>
                    )}
                    {/* A released result is never edited: it is corrected by a new result (once; then correct the latest). */}
                    {canManage && result.view === 'staff' && result.status === 'released' && !result.corrected_by_result_id && (
                      <Button variant="secondary" onClick={() => { setActionMessage(null); setFormMode({ kind: 'correct', original: result }) }}>Registar correção</Button>
                    )}
                  </div>
                </div>
                {open && <div id={`result-detail-${result.id}`}><ResultDetail result={result} patientArea={patientArea} /></div>}
              </li>
            )
          })}
        </ul>
      )}

      {pages > 1 && (
        <nav className="mt-4 flex items-center justify-between gap-3" aria-label="Paginação de resultados">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
          <span className="text-sm text-slate-500">Página {page} de {pages}</span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
        </nav>
      )}

      {releasing && (
        <ConfirmDialog
          title={releasing.corrects_result_id ? 'Disponibilizar correção' : 'Disponibilizar resultado'}
          description={releasing.corrects_result_id
            ? 'O paciente passa a ver esta correção, ligada ao resultado original (que se mantém visível como corrigido), e recebe uma notificação genérica. O motivo da correção não lhe é mostrado. Depois de disponibilizada, a correção não pode ser editada.'
            : 'O paciente passa a ver este resultado e recebe uma notificação genérica. Depois de disponibilizado, o resultado não pode ser editado; correções são registadas como novo resultado.'}
          confirmLabel="Disponibilizar"
          isPending={release.isPending}
          onCancel={() => setReleasing(null)}
          onConfirm={confirmRelease}
        />
      )}
    </section>
  )
}

function ResultSummary({ result }: { result: ClinicalResultPublic }) {
  const measurement = result.value ? [result.value, result.unit].filter(Boolean).join(' ') : null
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-slate-900">{result.title}</p>
        {result.view === 'staff' && (
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${result.status === 'released' ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-800'}`}>
            {result.status === 'released' ? 'Disponibilizado' : 'Rascunho'}
          </span>
        )}
        {result.corrects_result_id && <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-800">Correção</span>}
        {(result.view === 'staff' ? result.superseded : Boolean(result.superseded_by_result_id)) && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">Corrigido</span>
        )}
        {result.view === 'staff' && result.corrected_by_result_id && !result.superseded && (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">Correção em rascunho</span>
        )}
      </div>
      <p className="text-sm text-slate-600">{RESULT_CATEGORY_LABELS[result.category]} · {formatDate(result.result_date)}</p>
      {measurement && <p className="text-sm text-slate-700">{measurement}{result.reference_range ? ` (referência: ${result.reference_range})` : ''}</p>}
    </div>
  )
}

function ResultDetail({ result, patientArea }: { result: ClinicalResultPublic; patientArea: boolean }) {
  const supersededBy = result.view === 'staff' ? (result.superseded ? result.corrected_by_result_id : null) : result.superseded_by_result_id
  const resultLink = (id: string) => (patientArea ? `/patient/resultados?result=${encodeURIComponent(id)}` : `?result=${encodeURIComponent(id)}`)
  return (
    <dl className="mt-3 grid gap-3 rounded-lg bg-slate-50 p-4 text-sm sm:grid-cols-2">
      {supersededBy && (
        <div className="sm:col-span-2">
          <dt className="text-slate-500">Estado</dt>
          <dd className="text-slate-900">
            Este resultado foi corrigido. <Link to={resultLink(supersededBy)} className="font-medium text-teal-700 hover:underline">Ver a versão corrigida</Link>
          </dd>
        </div>
      )}
      {result.corrects_result_id && (
        <div className="sm:col-span-2">
          <dt className="text-slate-500">Correção</dt>
          <dd className="text-slate-900">
            Corrige um resultado anterior. <Link to={resultLink(result.corrects_result_id)} className="font-medium text-teal-700 hover:underline">Ver o resultado original</Link>
          </dd>
        </div>
      )}
      {result.view === 'staff' && result.correction_reason && (
        <div className="sm:col-span-2">
          <dt className="text-slate-500">Motivo da correção (interno)</dt>
          <dd className="whitespace-pre-wrap text-slate-900">{result.correction_reason}</dd>
        </div>
      )}
      {result.summary && (
        <div className="sm:col-span-2">
          <dt className="text-slate-500">Resumo clínico</dt>
          <dd className="whitespace-pre-wrap text-slate-900">{result.summary}</dd>
        </div>
      )}
      <div><dt className="text-slate-500">Responsável</dt><dd className="text-slate-900">{result.author_name}</dd></div>
      {result.released_at && (
        <div>
          <dt className="text-slate-500">Disponibilizado em</dt>
          <dd className="text-slate-900">
            {formatDateTime(result.released_at)}
            {result.view === 'staff' && result.released_by_name ? ` por ${result.released_by_name}` : ''}
          </dd>
        </div>
      )}
      {result.document_id && (
        <div className="sm:col-span-2">
          <dt className="text-slate-500">Documento associado</dt>
          <dd>
            {patientArea
              ? <Link to={`/patient/documentos?document=${encodeURIComponent(result.document_id)}`} className="font-medium text-teal-700 hover:underline">Abrir documento</Link>
              : <span className="text-slate-900">Disponível no separador Documentos.</span>}
          </dd>
        </div>
      )}
    </dl>
  )
}

function ResultForm({ patientId, mode, onDone }: { patientId: string; mode: FormMode | null; onDone: (message: string) => void }) {
  const create = useCreateClinicalResult(patientId)
  const update = useUpdateClinicalResult(patientId)
  const correct = useCorrectClinicalResult(patientId)
  // The patient's own documents only; the backend refuses any other document.
  const documents = usePatientDocuments(patientId, 1, 100)
  const editing = mode?.kind === 'edit' ? mode.result : null
  const correcting = mode?.kind === 'correct' ? mode.original : null
  const isCorrection = Boolean(correcting || editing?.corrects_result_id)
  const [form, setForm] = useState<ResultFormState>(
    editing ? formFromResult(editing) : correcting ? { ...formFromResult(correcting), correction_reason: '' } : EMPTY_RESULT_FORM,
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState('')
  const saving = create.isPending || update.isPending || correct.isPending

  function setField<K extends keyof ResultFormState>(key: K, value: ResultFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
    if (errors[key as string]) setErrors((current) => ({ ...current, [key as string]: '' }))
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setMessage('')
    const found = validateResultForm(form, { correction: isCorrection })
    setErrors(found)
    if (Object.values(found).some(Boolean)) return
    const onError = (error: unknown) => setMessage(resultErrorMessage(error))
    if (editing) {
      const payload = toCreatePayload(form)
      update.mutate(
        {
          id: editing.id,
          payload: {
            category: payload.category,
            title: payload.title,
            value: payload.value ?? null,
            unit: payload.unit ?? null,
            reference_range: payload.reference_range ?? null,
            summary: payload.summary ?? null,
            result_date: payload.result_date,
            document_id: payload.document_id ?? null,
            ...(editing.corrects_result_id ? { correction_reason: form.correction_reason.trim() } : {}),
          },
        },
        { onSuccess: () => onDone('Rascunho atualizado.'), onError },
      )
      return
    }
    if (correcting) {
      const payload: ClinicalResultCorrectionRequest = { ...toCreatePayload(form), correction_reason: form.correction_reason.trim() }
      correct.mutate(
        { id: correcting.id, payload },
        {
          onSuccess: (created) => onDone(created.status === 'released'
            ? 'Correção registada e disponibilizada ao paciente. O resultado original mantém-se como corrigido.'
            : 'Correção guardada como rascunho. O resultado original mantém-se inalterado.'),
          onError,
        },
      )
      return
    }
    create.mutate(toCreatePayload(form), {
      onSuccess: (created) => {
        setForm(EMPTY_RESULT_FORM)
        onDone(created.status === 'released' ? 'Resultado registado e disponibilizado ao paciente.' : 'Resultado guardado como rascunho.')
      },
      onError,
    })
  }

  const formLabel = editing ? (editing.corrects_result_id ? 'Editar correção' : 'Editar resultado') : correcting ? 'Registar correção' : 'Registar resultado'
  const submitLabel = editing ? 'Guardar rascunho' : correcting ? 'Registar correção' : 'Registar resultado'

  return (
    <form className="mb-6 grid gap-4 border-b border-slate-100 pb-6 sm:grid-cols-2" onSubmit={submit} noValidate aria-label={formLabel}>
      {correcting && (
        <p role="note" className="rounded-md bg-sky-50 p-3 text-sm text-sky-900 sm:col-span-2">
          A correção é registada como um novo resultado ligado a «{correcting.title}». O resultado original não é alterado e continua visível para o paciente, marcado como corrigido.
        </p>
      )}
      <SelectField label="Tipo de resultado" value={form.category} onChange={(event) => setField('category', event.target.value as ClinicalResultCategory)}>
        {Object.entries(RESULT_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField>
      <TextField label="Designação" required maxLength={RESULT_TITLE_MAX_LENGTH} value={form.title} error={errors.title} onChange={(event) => setField('title', event.target.value)} />
      <TextField label="Valor" maxLength={RESULT_VALUE_MAX_LENGTH} value={form.value} error={errors.value} onChange={(event) => setField('value', event.target.value)} />
      <TextField label="Unidade" maxLength={RESULT_UNIT_MAX_LENGTH} value={form.unit} error={errors.unit} onChange={(event) => setField('unit', event.target.value)} />
      <TextField label="Intervalo de referência" maxLength={RESULT_REFERENCE_MAX_LENGTH} value={form.reference_range} onChange={(event) => setField('reference_range', event.target.value)} />
      <TextField label="Data do resultado" required type="date" max={todayIso()} value={form.result_date} error={errors.result_date} onChange={(event) => setField('result_date', event.target.value)} />
      <div className="sm:col-span-2">
        <TextAreaField label="Resumo clínico" maxLength={RESULT_SUMMARY_MAX_LENGTH} value={form.summary} onChange={(event) => setField('summary', event.target.value)} />
      </div>
      {isCorrection && (
        <div className="sm:col-span-2">
          <TextAreaField label="Motivo da correção" required maxLength={CORRECTION_REASON_MAX_LENGTH} value={form.correction_reason} error={errors.correction_reason} onChange={(event) => setField('correction_reason', event.target.value)} />
          <p className="mt-1 text-xs text-slate-500">Fica no histórico da equipa clínica; não é mostrado ao paciente.</p>
        </div>
      )}
      <SelectField label="Documento associado (opcional)" value={form.document_id} onChange={(event) => setField('document_id', event.target.value)} disabled={documents.isLoading}>
        <option value="">Sem documento</option>
        {documents.data?.items.map((document) => <option key={document.id} value={document.id}>{document.title}</option>)}
      </SelectField>
      {!editing && (
        <label className="flex items-center gap-2 self-end text-sm text-slate-700">
          <input type="checkbox" checked={form.release} onChange={(event) => setField('release', event.target.checked)} className="h-4 w-4 rounded border-slate-300" />
          Disponibilizar já ao paciente
        </label>
      )}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" isLoading={saving}>{submitLabel}</Button>
        {mode && <Button variant="secondary" disabled={saving} onClick={() => onDone('')}>{correcting ? 'Cancelar correção' : 'Cancelar edição'}</Button>}
        {message && <p role="alert" className="text-sm text-red-700">{message}</p>}
      </div>
    </form>
  )
}
