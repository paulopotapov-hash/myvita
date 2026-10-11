import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../../../components/Button'
import { ChatComposer } from '../../../components/chat/ChatComposer'
import { ChatHeader } from '../../../components/chat/ChatHeader'
import { DateSeparator } from '../../../components/chat/DateSeparator'
import { MessageBubble } from '../../../components/chat/MessageBubble'
import { EmptyState } from '../../../components/EmptyState'
import { ErrorState } from '../../../components/ErrorState'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useConversationMessages, useMarkConversationRead } from '../../../hooks/useMessages'
import { ApiError } from '../../../lib/apiClient'
import { dayKey, daySeparatorLabel } from '../../../lib/chatFormat'
import { toUserMessage } from '../../../lib/errorMessages'
import { CLOSED_CONVERSATION_MESSAGE, INACTIVE_CONVERSATION_MESSAGE, patientStatusLabel } from '../../../lib/messaging'
import type { ConversationStatus, MessagePublic } from '../../../types/api'

const INBOX = '/patient/mensagens'

const STATUS_DESCRIPTIONS: Record<ConversationStatus, string> = {
  open: 'A conversa está ativa. A equipa clínica lê e responde às suas mensagens.',
  waiting_for_team: 'A sua mensagem foi enviada à equipa clínica, que responderá assim que possível.',
  waiting_for_patient: 'A equipa clínica respondeu. Pode continuar a conversa.',
  closed: 'A equipa clínica encerrou esta conversa. Pode consultá-la, mas não enviar mensagens. Se precisar, contacte a clínica.',
}

function sameAuthor(a: MessagePublic | undefined, b: MessagePublic | undefined): boolean {
  return Boolean(a && b && a.is_mine === b.is_mine && a.sender_name === b.sender_name && a.sender_role === b.sender_role)
}

/** Patient conversation, chat style: day separators, bubbles, composer fixed at the bottom. */
export function PatientConversation() {
  const { conversationId = '' } = useParams()
  const thread = useConversationMessages(conversationId)
  const markRead = useMarkConversationRead(conversationId)
  const endRef = useRef<HTMLDivElement>(null)

  const firstPage = thread.data?.pages[0]
  const unreadCount = firstPage?.conversation.unread_count ?? 0
  const total = firstPage?.total ?? 0
  // Mark incoming messages read once per (conversation, message total).
  const attemptedRef = useRef<string | null>(null)
  const { mutate: markReadMutate } = markRead
  useEffect(() => {
    const key = `${conversationId}:${total}`
    if (unreadCount > 0 && attemptedRef.current !== key) {
      attemptedRef.current = key
      markReadMutate()
    }
  }, [conversationId, total, unreadCount, markReadMutate])

  // Pages are newest-first; dedupe (pages shift as new messages arrive) and show oldest-first.
  const seen = new Set<string>()
  const messages: MessagePublic[] = []
  for (const page of thread.data?.pages ?? []) {
    for (const message of page.conversation.messages) {
      if (!seen.has(message.id)) {
        seen.add(message.id)
        messages.push(message)
      }
    }
  }
  messages.reverse()

  // Scroll to the newest message on open and when a new one arrives, never when older history loads.
  const newestId = messages[messages.length - 1]?.id
  useEffect(() => {
    if (newestId) endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [newestId])

  const backLink = (
    <Link to={INBOX} className="text-base font-medium text-teal-800 hover:underline">
      ← Voltar às mensagens
    </Link>
  )
  if (thread.isLoading) return <LoadingSpinner label="A carregar conversa…" />
  if (thread.isError && !firstPage) {
    // 403/404 look identical on purpose: the backend never says whether a conversation that isn't yours exists.
    const inaccessible = thread.error instanceof ApiError && (thread.error.status === 404 || thread.error.status === 403)
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        {backLink}
        {inaccessible ? (
          <EmptyState title="Conversa não encontrada" description="Esta conversa não existe ou não tem acesso a ela." />
        ) : (
          <ErrorState message={toUserMessage(thread.error)} onRetry={() => thread.refetch()} />
        )}
      </div>
    )
  }
  if (!firstPage) return null

  const conversation = firstPage.conversation
  return (
    <div className="mx-auto -my-6 flex min-h-[calc(100dvh-4rem)] w-full max-w-3xl flex-col">
      <ChatHeader
        backTo={INBOX}
        name={conversation.staff_name}
        subtitle={`Equipa clínica · ${patientStatusLabel(conversation.status)}`}
        statusLabel={patientStatusLabel(conversation.status)}
        statusDescription={STATUS_DESCRIPTIONS[conversation.status]}
      />

      <section aria-labelledby="messages-heading" className="flex flex-1 flex-col gap-3 py-4">
        <h2 id="messages-heading" className="sr-only">Histórico de mensagens</h2>
        {thread.hasNextPage && (
          <div className="flex justify-center">
            <Button variant="secondary" isLoading={thread.isFetchingNextPage} onClick={() => thread.fetchNextPage()}>
              Carregar mensagens anteriores
            </Button>
          </div>
        )}
        {thread.isFetchNextPageError && <p role="alert" className="text-center text-sm text-red-700">{toUserMessage(thread.error)}</p>}
        {messages.length === 0 ? (
          <EmptyState title="Ainda não há mensagens" description="A sua equipa clínica ainda não escreveu nesta conversa." />
        ) : (
          <ol className="flex flex-col gap-1.5" aria-label="Mensagens">
            {messages.map((message, index) => {
              const previous = messages[index - 1]
              const next = messages[index + 1]
              const newDay = !previous || dayKey(previous.created_at) !== dayKey(message.created_at)
              const lastOfDay = !next || dayKey(next.created_at) !== dayKey(message.created_at)
              return [
                newDay && <DateSeparator key={`day-${message.id}`} label={daySeparatorLabel(message.created_at)} />,
                <MessageBubble
                  key={message.id}
                  message={message}
                  showSender={newDay || !sameAuthor(previous, message)}
                  showAvatar={lastOfDay || !sameAuthor(next, message)}
                />,
              ]
            })}
          </ol>
        )}
        <div ref={endRef} />
      </section>

      {conversation.can_reply ? (
        <ChatComposer conversationId={conversation.id} />
      ) : (
        // Closed, or (M2) nobody on the care team could read a reply. The backend rejects replies too.
        <p role="status" className="sticky bottom-0 -mx-4 border-t border-amber-200 bg-amber-50 p-4 text-base text-amber-900 md:-mx-8">
          {conversation.status === 'closed' ? CLOSED_CONVERSATION_MESSAGE : INACTIVE_CONVERSATION_MESSAGE}
        </p>
      )}
    </div>
  )
}
