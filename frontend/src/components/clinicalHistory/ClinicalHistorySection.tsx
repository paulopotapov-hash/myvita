import { Fragment, useState, type ReactNode } from 'react'
import { Button } from '../Button'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { FormMessage } from '../FormMessage'
import { LoadingSpinner } from '../LoadingSpinner'
import { ReasonDialog } from '../ReasonDialog'
import { EntryBadges } from './EntryBadges'
import { HistoryEntryForm } from './HistoryEntryForm'
import { useClinicalHistory, useClinicalHistoryAction, type HistoryAction } from '../../hooks/useClinicalHistory'
import { ApiError } from '../../lib/apiClient'
import {
  CATEGORY_FIELDS,
  CATEGORY_LABELS,
  CATEGORY_SINGULAR,
  CONDITION_STATUS_LABELS,
  HISTORY_CATEGORIES,
  SEVERITY_LABELS,
} from '../../lib/clinicalHistoryLabels'
import { toUserMessage } from '../../lib/errorMessages'
import { formatPartialDate } from '../../lib/partialDate'
import type { ClinicalHistoryEntry, ClinicalHistoryFields, HistoryCategory } from '../../types/api'

type Mode = 'patient' | 'staff'
type Editing = { kind: 'create'; category: HistoryCategory } | { kind: 'edit'; entry: ClinicalHistoryEntry }
type Dialog = { kind: 'hide' | 'remove'; entry: ClinicalHistoryEntry }

interface Props {
  patientId: string
  /** "patient": read, declare and change own unconfirmed declarations. "staff": doctors and nurses. */
  mode: Mode
  /** Rendered between "Cirurgias e procedimentos" and "Alergias" (the medication category). */
  medicationSlot?: ReactNode
}

function summary(entry: ClinicalHistoryEntry): { title: string; details: string[] } {
  const details: string[] = []
  const onset = formatPartialDate(entry.onset)
  const resolved = formatPartialDate(entry.resolved)
  const occurred = formatPartialDate(entry.occurred)
  if (entry.condition_status) details.push(CONDITION_STATUS_LABELS[entry.condition_status])
  if (onset) details.push(`Início ${onset}`)
  if (resolved) details.push(`Resolvida ${resolved}`)
  if (occurred) details.push(occurred)
  if (entry.location) details.push(entry.location)
  if (entry.reaction) details.push(`Reação: ${entry.reaction}`)
  if (entry.severity) details.push(SEVERITY_LABELS[entry.severity])
  return { title: entry.category === 'note' ? (entry.note_text ?? '') : (entry.name ?? ''), details }
}

function fieldsOf(entry: ClinicalHistoryEntry): Partial<ClinicalHistoryFields> {
  return Object.fromEntries(CATEGORY_FIELDS[entry.category].map((key) => [key, entry[key]]))
}

/**
 * Clinical history by category (D1): conditions, procedures, [medication], allergies,
 * vaccines and notes. Every entry says whether a professional confirmed it or the
 * patient declared it. The care team also sees, and manages, entries hidden from the patient (D4).
 */
export function ClinicalHistorySection({ patientId, mode, medicationSlot }: Props) {
  const history = useClinicalHistory(patientId)
  const action = useClinicalHistoryAction(patientId)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [dialogError, setDialogError] = useState('')
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const staff = mode === 'staff'
  const busy = action.isPending

  function run(variables: HistoryAction, success: string) {
    setMessage(null)
    action.mutate(variables, {
      onSuccess: () => {
        setEditing(null)
        setDialog(null)
        setServerErrors({})
        setMessage({ kind: 'success', text: success })
      },
      onError: (error) => {
        if (dialog) setDialogError(toUserMessage(error))
        else if (editing && error instanceof ApiError && error.fieldErrors) setServerErrors(error.fieldErrors)
        else if (editing) setServerErrors({ _root: toUserMessage(error) })
        else setMessage({ kind: 'error', text: toUserMessage(error) })
      },
    })
  }

  function startCreate(category: HistoryCategory) {
    setMessage(null)
    setServerErrors({})
    setEditing({ kind: 'create', category })
  }

  const entries = history.data ?? []

  function renderEntry(entry: ClinicalHistoryEntry) {
    const { title, details } = summary(entry)
    const describedBy = `history-${entry.id}`
    if (editing?.kind === 'edit' && editing.entry.id === entry.id) {
      return (
        <li key={entry.id} className="py-3">
          <HistoryEntryForm
            category={entry.category}
            initial={fieldsOf(entry)}
            submitLabel="Guardar alterações"
            isPending={busy}
            serverErrors={serverErrors}
            onCancel={() => setEditing(null)}
            onSubmit={(values) => run({ kind: 'update', id: entry.id, payload: { ...values, expected_version: entry.version } }, 'Entrada atualizada.')}
          />
        </li>
      )
    }
    const canChange = staff || (entry.view === 'patient' && entry.can_edit)
    return (
      <li key={entry.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
        <div className="min-w-0">
          <p id={describedBy} className={`font-medium text-slate-900 ${entry.category === 'note' ? 'whitespace-pre-wrap' : ''}`}>{title}</p>
          {details.length > 0 && <p className="text-sm text-slate-600">{details.join(' · ')}</p>}
          <div className="mt-1"><EntryBadges confirmed={entry.confirmed} hidden={entry.view === 'staff' && entry.hidden} /></div>
          {entry.view === 'staff' && entry.hidden && entry.hidden_reason && (
            <p className="mt-1 text-sm text-slate-600">Motivo para ocultar: {entry.hidden_reason}{entry.hidden_by_name ? ` (${entry.hidden_by_name})` : ''}</p>
          )}
          {entry.confirmed && entry.confirmed_by_name && <p className="text-xs text-slate-500">Confirmado por {entry.confirmed_by_name}</p>}
        </div>
        {canChange && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" aria-describedby={describedBy} disabled={busy} onClick={() => { setMessage(null); setServerErrors({}); setEditing({ kind: 'edit', entry }) }}>Editar</Button>
            {staff && !entry.confirmed && (
              <Button variant="secondary" aria-describedby={describedBy} disabled={busy} onClick={() => run({ kind: 'confirm', id: entry.id, version: entry.version }, 'Entrada confirmada.')}>Confirmar</Button>
            )}
            {staff && entry.view === 'staff' && (entry.hidden ? (
              <Button variant="secondary" aria-describedby={describedBy} disabled={busy} onClick={() => run({ kind: 'show', id: entry.id, version: entry.version }, 'A entrada voltou a estar visível para o paciente.')}>Mostrar ao paciente</Button>
            ) : (
              <Button variant="secondary" aria-describedby={describedBy} disabled={busy} onClick={() => { setDialogError(''); setDialog({ kind: 'hide', entry }) }}>Ocultar ao paciente</Button>
            ))}
            <Button variant="secondary" aria-describedby={describedBy} disabled={busy} onClick={() => { setDialogError(''); setDialog({ kind: 'remove', entry }) }}>Apagar</Button>
          </div>
        )}
      </li>
    )
  }

  function renderCategory(category: HistoryCategory) {
    const items = entries.filter((entry) => entry.category === category)
    const headingId = `history-${category}`
    const addLabel = `${staff ? 'Adicionar' : 'Declarar'} ${CATEGORY_SINGULAR[category]}`
    return (
      <section key={category} aria-labelledby={headingId} className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={headingId} className="text-base font-semibold text-slate-900">{CATEGORY_LABELS[category]}</h2>
          {!(editing?.kind === 'create' && editing.category === category) && (
            <Button variant="secondary" disabled={busy} onClick={() => startCreate(category)}>{addLabel}</Button>
          )}
        </div>
        {editing?.kind === 'create' && editing.category === category && (
          <div className="mt-3">
            {!staff && <p className="mb-2 text-sm text-slate-500">Fica como «Declarado pelo paciente» até a equipa clínica confirmar.</p>}
            <HistoryEntryForm
              category={category}
              submitLabel={addLabel}
              isPending={busy}
              serverErrors={serverErrors}
              onCancel={() => setEditing(null)}
              onSubmit={(values) => run({ kind: 'create', payload: { category, ...values } }, staff ? 'Entrada adicionada.' : 'Declaração registada.')}
            />
          </div>
        )}
        {history.data && items.length === 0 && <p className="mt-2 text-sm text-slate-500">Sem registos.</p>}
        {items.length > 0 && <ul className="mt-1 divide-y divide-slate-100">{items.map(renderEntry)}</ul>}
      </section>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {message && <FormMessage kind={message.kind}>{message.text}</FormMessage>}
      {history.isLoading && <LoadingSpinner label="A carregar o histórico clínico…" />}
      {history.isError && <ErrorState message={toUserMessage(history.error)} onRetry={() => history.refetch()} />}
      {history.data && entries.length === 0 && !staff && !medicationSlot && (
        <EmptyState title="Ainda sem histórico clínico" description="Podes declarar doenças, cirurgias, alergias, vacinas ou outras notas." />
      )}
      {history.data &&
        HISTORY_CATEGORIES.map((category) => (
          <Fragment key={category}>
            {renderCategory(category)}
            {category === 'procedure' && medicationSlot}
          </Fragment>
        ))}

      {dialog?.kind === 'hide' && (
        <ReasonDialog
          title="Ocultar ao paciente"
          description="A entrada deixa de aparecer ao paciente até a voltares a mostrar. O motivo fica registado."
          confirmLabel="Ocultar"
          reasonLabel="Motivo"
          isPending={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) => run({ kind: 'hide', id: dialog.entry.id, version: dialog.entry.version, reason }, 'Entrada ocultada ao paciente.')}
        />
      )}
      {dialog?.kind === 'remove' && (
        <ReasonDialog
          title={staff ? 'Apagar entrada' : 'Apagar declaração'}
          description="A entrada deixa de aparecer no histórico. A remoção fica registada."
          confirmLabel="Apagar"
          reasonLabel={staff ? 'Motivo' : undefined}
          isPending={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={(reason) => run({ kind: 'remove', id: dialog.entry.id, version: dialog.entry.version, reason: reason || undefined }, 'Entrada apagada.')}
        />
      )}
    </div>
  )
}
