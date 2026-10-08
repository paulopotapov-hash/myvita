import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { useConversationMessages, useMarkConversationRead, useSendMessage } from '../../hooks/useMessages'
import { useSession } from '../../hooks/useSession'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import { canUseMessaging, messagesBasePath, otherParticipantName } from '../../lib/messaging'
import { MESSAGE_MAX_LENGTH } from '../../types/api'
import type { MessagePublic } from '../../types/api'

export function ConversationPage() {
  const { conversationId = '' } = useParams()
  const { user } = useSession()
  const allowed = canUseMessaging(user)
  const thread = useConversationMessages(allowed ? conversationId : '')
  const markRead = useMarkConversationRead(conversationId)

  const firstPage = thread.data?.pages[0]
  const unreadCount = firstPage?.conversation.unread_count ?? 0
  const total = firstPage?.total ?? 0
  // Mark incoming messages read once per (conversation, message total): a
  // new incoming message changes the total and triggers it again, while a
  // failed attempt is not retried in a loop.
  const attemptedRef = useRef<string | null>(null)
  const { mutate: markReadMutate } = markRead
  useEffect(() => {
    const key = `${conversationId}:${total}`
    if (unreadCount > 0 && attemptedRef.current !== key) {
      attemptedRef.current = key
      markReadMutate()
    }
  }, [conversationId, total, unreadCount, markReadMutate])

  if (!user) return null
  const basePath = messagesBasePath(user)
  const backLink = (
    <Link to={basePath} className="text-sm font-medium text-teal-800 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700">
      ← Voltar às mensagens
    </Link>
  )

  if (!allowed) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        {backLink}
        <EmptyState title="Mensagens não disponíveis para o seu perfil" />
      </div>
    )
  }
  if (thread.isLoading) return <LoadingSpinner label="A carregar conversa…" />
  // Only a failed first load replaces the page; a failed "load older" keeps the thread visible.
  if (thread.isError && !firstPage) {
    // 403/404 look identical on purpose: the backend never says whether a
    // conversation that isn't yours exists, and neither does the UI.
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
  const otherName = otherParticipantName(conversation, user)
  const seen = new Set<string>()
  const messages: MessagePublic[] = []
  // Pages are newest-first; dedupe (pages shift as new messages arrive) and show oldest-first.
  for (const page of thread.data?.pages ?? []) {
    for (const message of page.conversation.messages) {
      if (!seen.has(message.id)) {
        seen.add(message.id)
        messages.push(message)
      }
    }
  }
  messages.reverse()

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      {backLink}
      <header>
        <h1 className="break-words text-2xl font-semibold text-slate-900">{otherName}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {user.role === 'patient' ? 'Conversa com o seu profissional de saúde' : `Conversa com o paciente ${conversation.patient_name}`}
        </p>
      </header>

      <section aria-labelledby="messages-heading" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
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
          <EmptyState title="Ainda não há mensagens" description="Escreva a primeira mensagem desta conversa." />
        ) : (
          <ol className="flex flex-col gap-3" aria-label="Mensagens">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} own={message.sender_user_id === user.id} otherName={otherName} />
            ))}
          </ol>
        )}
      </section>

      <Composer conversationId={conversation.id} />
    </div>
  )
}

function MessageBubble({ message, own, otherName }: { message: MessagePublic; own: boolean; otherName: string }) {
  return (
    <li className={`flex ${own ? 'justify-end' : 'justify-start'}`}>
      <article
        aria-label={own ? 'Mensagem enviada por si' : `Mensagem de ${otherName}`}
        className={`max-w-[85%] min-w-0 rounded-lg px-4 py-3 sm:max-w-[75%] ${own ? 'bg-teal-700 text-white' : 'border border-slate-200 bg-slate-50 text-slate-900'}`}
      >
        <p className={`text-xs font-semibold ${own ? 'text-teal-50' : 'text-slate-700'}`}>{own ? 'Você' : otherName}</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-sm">{message.body}</p>
        <p className={`mt-2 text-xs ${own ? 'text-teal-50' : 'text-slate-600'}`}>
          <time dateTime={message.created_at}>{formatDateTime(message.created_at)}</time>
          {own && <span> · {message.read_at ? 'Lida' : 'Enviada'}</span>}
        </p>
      </article>
    </li>
  )
}

function Composer({ conversationId }: { conversationId: string }) {
  const send = useSendMessage(conversationId)
  const [body, setBody] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const trimmed = body.trim()

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (!trimmed) {
      setValidationError('Escreva uma mensagem antes de enviar.')
      return
    }
    if (trimmed.length > MESSAGE_MAX_LENGTH) {
      setValidationError(`A mensagem não pode exceder ${MESSAGE_MAX_LENGTH} caracteres.`)
      return
    }
    setValidationError(null)
    send.mutate(trimmed, { onSuccess: () => setBody('') })
  }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit()
  }
  const error = validationError ?? (send.isError ? toUserMessage(send.error) : null)

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 sm:p-6" aria-label="Enviar mensagem">
      <label htmlFor="message-body" className="text-sm font-medium text-slate-700">Mensagem</label>
      <textarea
        id="message-body"
        value={body}
        onChange={(event) => {
          setBody(event.target.value)
          if (validationError) setValidationError(null)
        }}
        onKeyDown={onKeyDown}
        maxLength={MESSAGE_MAX_LENGTH}
        rows={3}
        aria-invalid={Boolean(error)}
        aria-describedby={`message-body-hint${error ? ' message-body-error' : ''}`}
        className="w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-600"
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p id="message-body-hint" className="text-xs text-slate-600">
          {body.length}/{MESSAGE_MAX_LENGTH} caracteres · Ctrl+Enter para enviar
        </p>
        <Button type="submit" isLoading={send.isPending} disabled={!trimmed}>Enviar</Button>
      </div>
      {error && <p id="message-body-error" role="alert" className="text-sm text-red-700">{error}</p>}
    </form>
  )
}
