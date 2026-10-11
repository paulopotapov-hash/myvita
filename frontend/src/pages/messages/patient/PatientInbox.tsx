import { useState } from 'react'
import { Button } from '../../../components/Button'
import { ConversationListItem } from '../../../components/chat/ConversationListItem'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorState } from '../../../components/ErrorState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useConversations } from '../../../hooks/useMessages'
import { toUserMessage } from '../../../lib/errorMessages'

const PAGE_SIZE = 20

/** Patient conversation list, chat style. Patients reply in threads opened by their care team. */
export function PatientInbox() {
  const [page, setPage] = useState(1)
  const conversations = useConversations(page, PAGE_SIZE)
  const total = conversations.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <h1 className="text-2xl font-semibold text-slate-900">Mensagens</h1>
      {conversations.isLoading && <LoadingSpinner label="A carregar conversas…" />}
      {conversations.isError && <ErrorState message={toUserMessage(conversations.error)} onRetry={() => conversations.refetch()} />}
      {conversations.data?.items.length === 0 && (
        <EmptyState
          title="Ainda não tem conversas"
          description="A sua equipa clínica inicia as conversas consigo. Quando o fizer, aparecem aqui."
        />
      )}
      {conversations.data && conversations.data.items.length > 0 && (
        <ul className="-mx-3 flex flex-col" aria-label="Conversas">
          {conversations.data.items.map((conversation) => (
            <ConversationListItem key={conversation.id} conversation={conversation} to={`/patient/mensagens/${conversation.id}`} />
          ))}
        </ul>
      )}
      {total > PAGE_SIZE && (
        <nav aria-label="Paginação de conversas" className="flex items-center justify-between gap-3">
          <Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
          <span className="text-base text-slate-600">Página {page} de {pages}</span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
        </nav>
      )}
    </div>
  )
}
