import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useAuditLogs } from '../../hooks/useAuditLogs'
import { AUDIT_ACTION_LABELS, AUDIT_RESOURCE_TYPES, AUDIT_RESULT_LABELS, auditActionLabel } from '../../lib/auditLabels'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import type { AuditLogFilters } from '../../services/auditLogs'
import type { AuditLogPublic } from '../../types/api'

const PAGE_SIZE = 25
const EMPTY: Required<AuditLogFilters> = { action: '', actorUserId: '', resourceType: '', resourceId: '', dateFrom: '', dateTo: '' }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const selectClass = 'rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600'

function resultBadge(result: AuditLogPublic['result']) {
  const tone = result === 'success' ? 'bg-teal-50 text-teal-800' : result === 'denied' ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-700'
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{AUDIT_RESULT_LABELS[result]}</span>
}

function metadataSummary(metadata: Record<string, unknown> | null): string {
  if (!metadata) return ''
  return Object.entries(metadata)
    .map(([key, value]) => `${key}: ${typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)}`)
    .join(' · ')
}

function actorLine(actor: AuditLogPublic['actor']) {
  if (!actor.email && !actor.name) return <span>Sistema / anónimo</span>
  return (
    <>
      {actor.name && <span className="font-medium text-slate-800">{actor.name}</span>}
      {actor.name && actor.email && <span aria-hidden="true"> · </span>}
      {actor.email && <span className="break-all">{actor.email}</span>}
    </>
  )
}

export function AuditLogPage() {
  const [draft, setDraft] = useState<Required<AuditLogFilters>>(EMPTY)
  const [filters, setFilters] = useState<AuditLogFilters>({})
  const [filterError, setFilterError] = useState('')
  const [page, setPage] = useState(1)
  const logs = useAuditLogs(page, PAGE_SIZE, filters)
  const total = logs.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function applyFilters(event: React.FormEvent) {
    event.preventDefault()
    if ((draft.actorUserId && !UUID.test(draft.actorUserId)) || (draft.resourceId && !UUID.test(draft.resourceId))) {
      setFilterError('Os identificadores têm de ser UUIDs válidos.')
      return
    }
    if (draft.dateFrom && draft.dateTo && draft.dateFrom > draft.dateTo) {
      setFilterError('A data inicial tem de ser anterior à data final.')
      return
    }
    setFilterError('')
    setPage(1)
    setFilters(Object.fromEntries(Object.entries(draft).filter(([, value]) => value)) as AuditLogFilters)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Auditoria</h1>
        <p className="text-sm text-slate-500">Registo de acessos e ações na sua clínica. Apenas identificadores — nunca conteúdos clínicos.</p>
      </div>

      <form onSubmit={applyFilters} aria-label="Filtros de auditoria" className="grid gap-3 rounded-xl border border-slate-200 bg-white p-6 sm:grid-cols-2 lg:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">Ação
          <select className={selectClass} value={draft.action} onChange={(e) => setDraft((d) => ({ ...d, action: e.target.value }))}>
            <option value="">Todas</option>
            {Object.entries(AUDIT_ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">Tipo de recurso
          <select className={selectClass} value={draft.resourceType} onChange={(e) => setDraft((d) => ({ ...d, resourceType: e.target.value }))}>
            <option value="">Todos</option>
            {AUDIT_RESOURCE_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <TextField label="ID do recurso" value={draft.resourceId} onChange={(e) => setDraft((d) => ({ ...d, resourceId: e.target.value.trim() }))} placeholder="UUID" />
        <TextField label="ID do utilizador (ator)" value={draft.actorUserId} onChange={(e) => setDraft((d) => ({ ...d, actorUserId: e.target.value.trim() }))} placeholder="UUID" />
        <TextField label="Desde" type="datetime-local" value={draft.dateFrom} onChange={(e) => setDraft((d) => ({ ...d, dateFrom: e.target.value }))} />
        <TextField label="Até" type="datetime-local" value={draft.dateTo} onChange={(e) => setDraft((d) => ({ ...d, dateTo: e.target.value }))} />
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-3">
          <Button type="submit">Filtrar</Button>
          <Button variant="secondary" onClick={() => { setDraft(EMPTY); setFilters({}); setFilterError(''); setPage(1) }}>Limpar</Button>
          {filterError && <p role="alert" className="text-sm text-red-700">{filterError}</p>}
          {logs.data && <p className="text-sm text-slate-500">{total} {total === 1 ? 'evento' : 'eventos'}</p>}
        </div>
      </form>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        {logs.isLoading && <LoadingSpinner label="A carregar auditoria…" />}
        {logs.isError && <ErrorState message={toUserMessage(logs.error)} onRetry={() => logs.refetch()} />}
        {logs.data?.items.length === 0 && <EmptyState title="Sem eventos" description="Não existem eventos de auditoria para os filtros escolhidos." />}
        {logs.data && logs.data.items.length > 0 && (
          <ul className="divide-y divide-slate-100" aria-label="Eventos de auditoria">
            {logs.data.items.map((entry) => (
              <li key={entry.id} className="flex flex-col gap-2 py-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">{auditActionLabel(entry.action)}</p>
                    {resultBadge(entry.result)}
                  </div>
                  <p className="text-sm text-slate-600">{actorLine(entry.actor)}{entry.resource_type && <> · {entry.resource_type}{entry.resource_id && <span className="font-mono text-xs"> {entry.resource_id}</span>}</>}</p>
                  {entry.metadata && <p className="truncate text-xs text-slate-500" title={metadataSummary(entry.metadata)}>{metadataSummary(entry.metadata)}</p>}
                </div>
                <div className="shrink-0 text-left text-xs text-slate-500 sm:text-right">
                  <p>{formatDateTime(entry.timestamp)}</p>
                  {entry.ip_address && <p>IP {entry.ip_address}</p>}
                  {entry.request_id && <p className="font-mono">{entry.request_id}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {logs.data && total > PAGE_SIZE && (
          <div className="mt-5 flex items-center justify-between gap-3">
            <Button variant="secondary" disabled={page === 1} onClick={() => setPage((v) => v - 1)}>Anterior</Button>
            <span className="text-sm text-slate-500">Página {page} de {pages}</span>
            <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((v) => v + 1)}>Seguinte</Button>
          </div>
        )}
      </section>
    </div>
  )
}
