import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextField } from '../../components/TextField'
import { useConversations, useCreateConversation, usePatientContactSearch } from '../../hooks/useMessages'
import { useSession } from '../../hooks/useSession'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { canUseMessaging, messagesBasePath, otherParticipantName } from '../../lib/messaging'
import type { ConversationPublic, UserPublic } from '../../types/api'

const PAGE_SIZE = 20

export function MessagesInboxPage() {
  const { user } = useSession()
  const allowed = canUseMessaging(user)
  const [page, setPage] = useState(1)
  const [composerOpen, setComposerOpen] = useState(false)
  const conversations = useConversations(page, PAGE_SIZE, allowed)

  if (!user) return null
  if (!allowed) {
    return (
      <MessagesShell>
        <EmptyState
          title="Mensagens não disponíveis para o seu perfil"
          description="As mensagens são trocadas entre pacientes e médicos ou enfermeiros da clínica."
        />
      </MessagesShell>
    )
  }

  const total = conversations.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const basePath = messagesBasePath(user)
  // M4: only clinical staff start conversations; patients reply in threads opened by staff.
  const canStart = user.role !== 'patient'

  return (
    <MessagesShell
      action={
        canStart ? (
          <Button variant={composerOpen ? 'secondary' : 'primary'} onClick={() => setComposerOpen((open) => !open)} aria-expanded={composerOpen} aria-controls="new-conversation">
            {composerOpen ? 'Fechar' : 'Nova conversa'}
          </Button>
        ) : undefined
      }
    >
      {canStart && composerOpen && <NewConversationPanel basePath={basePath} />}
      <section aria-labelledby="conversations-heading" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
        <h2 id="conversations-heading" className="sr-only">Conversas</h2>
        {conversations.isLoading && <LoadingSpinner label="A carregar conversas…" />}
        {conversations.isError && (
          <ErrorState message={toUserMessage(conversations.error)} onRetry={() => conversations.refetch()} />
        )}
        {conversations.data?.items.length === 0 && (
          <EmptyState
            title="Ainda não tem conversas"
            description={
              user.role === 'patient'
                ? 'A sua equipa clínica inicia as conversas consigo. Quando o fizer, aparecem aqui.'
                : 'Pode iniciar uma conversa com um paciente que acompanha.'
            }
          />
        )}
        {conversations.data && conversations.data.items.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {conversations.data.items.map((conversation) => (
              <ConversationRow key={conversation.id} conversation={conversation} user={user} basePath={basePath} />
            ))}
          </ul>
        )}
        {total > PAGE_SIZE && (
          <nav aria-label="Paginação de conversas" className="mt-5 flex items-center justify-between gap-3">
            <Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
            <span className="text-sm text-slate-500">Página {page} de {pages}</span>
            <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
          </nav>
        )}
      </section>
    </MessagesShell>
  )
}

function MessagesShell({ action, children }: { action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Mensagens</h1>
          <p className="mt-1 text-sm text-slate-600">Comunicação segura entre pacientes e a equipa clínica.</p>
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

function ConversationRow({ conversation, user, basePath }: { conversation: ConversationPublic; user: UserPublic; basePath: string }) {
  const unread = conversation.unread_count > 0
  const name = otherParticipantName(conversation, user)
  return (
    <li>
      <Link
        to={`${basePath}/${conversation.id}`}
        className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-md px-2 py-4 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700"
      >
        <div className="min-w-0">
          <p className={`break-words ${unread ? 'font-semibold text-slate-900' : 'font-medium text-slate-800'}`}>{name}</p>
          <p className="text-sm text-slate-600">{user.role === 'patient' ? 'Profissional de saúde' : 'Paciente'}</p>
          <p className="mt-1 text-xs text-slate-600">
            Última atividade: <time dateTime={conversation.updated_at}>{formatDateTime(conversation.updated_at)}</time>
          </p>
        </div>
        {unread ? (
          <span className="rounded-full bg-teal-100 px-2.5 py-0.5 text-xs font-semibold text-teal-900">
            {conversation.unread_count === 1 ? '1 não lida' : `${conversation.unread_count} não lidas`}
          </span>
        ) : (
          <span className="text-xs text-slate-600">Sem mensagens por ler</span>
        )}
      </Link>
    </li>
  )
}

/** Staff only (M3/M4): the backend also requires an active care assignment to the patient. */
function NewConversationPanel({ basePath }: { basePath: string }) {
  const navigate = useNavigate()
  const create = useCreateConversation()
  const start = (patientId: string) =>
    create.mutate({ patient_id: patientId }, { onSuccess: (conversation) => navigate(`${basePath}/${conversation.id}`) })

  return (
    <section id="new-conversation" aria-labelledby="new-conversation-heading" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <h2 id="new-conversation-heading" className="text-lg font-semibold text-slate-900">Nova conversa</h2>
      <PatientPicker onStart={start} isPending={create.isPending} />
      {create.isError && (
        <p role="alert" className="mt-3 text-sm text-red-700">{toUserMessage(create.error)}</p>
      )}
    </section>
  )
}

function PatientPicker({ onStart, isPending }: { onStart: (patientId: string) => void; isPending: boolean }) {
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const results = usePatientContactSearch(search)
  const patients = (results.data?.items ?? []).filter((patient) => patient.is_active)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setSearch(draft.trim())
  }
  return (
    <div className="mt-3 flex flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end" role="search">
        <div className="min-w-0 flex-1">
          <TextField label="Pesquisar paciente" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Nome do paciente" />
        </div>
        <Button type="submit" variant="secondary" disabled={!draft.trim()}>Pesquisar</Button>
      </form>
      {results.isLoading && <LoadingSpinner label="A pesquisar pacientes…" />}
      {results.isError && <ErrorState message={toUserMessage(results.error)} onRetry={() => results.refetch()} />}
      {results.isSuccess && patients.length === 0 && (
        <p className="text-sm text-slate-600">Nenhum paciente ativo encontrado.</p>
      )}
      {patients.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Pacientes encontrados">
          {patients.map((patient) => (
            <li key={patient.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 py-3">
              <span className="break-words font-medium text-slate-800">{patient.full_name}</span>
              <Button variant="secondary" isLoading={isPending} onClick={() => onStart(patient.id)} aria-label={`Iniciar conversa com ${patient.full_name}`}>
                Iniciar conversa
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
