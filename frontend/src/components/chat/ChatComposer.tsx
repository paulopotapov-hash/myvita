import { useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useSendMessage } from '../../hooks/useMessages'
import { ApiError } from '../../lib/apiClient'
import { toUserMessage } from '../../lib/errorMessages'
import { INACTIVE_CONVERSATION_MESSAGE } from '../../lib/messaging'
import { MESSAGE_MAX_LENGTH } from '../../types/api'
import { Icon } from '../Icon'

const MAX_HEIGHT = 160 // about five lines, then the field scrolls

/** Composer fixed at the bottom of the conversation: growing text field and a round send button. */
export function ChatComposer({ conversationId }: { conversationId: string }) {
  const send = useSendMessage(conversationId)
  const [body, setBody] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const fieldRef = useRef<HTMLTextAreaElement>(null)
  const trimmed = body.trim()

  useLayoutEffect(() => {
    const field = fieldRef.current
    if (!field) return
    field.style.height = 'auto'
    field.style.height = `${Math.min(field.scrollHeight, MAX_HEIGHT)}px`
  }, [body])

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
  const refused = send.error instanceof ApiError && send.error.status === 403
  const error = validationError ?? (send.isError ? (refused ? (send.error as ApiError).detail ?? INACTIVE_CONVERSATION_MESSAGE : toUserMessage(send.error)) : null)
  const nearLimit = body.length > MESSAGE_MAX_LENGTH - 500

  return (
    <form
      onSubmit={submit}
      aria-label="Enviar mensagem"
      className="sticky bottom-0 z-10 -mx-4 border-t border-slate-100 bg-slate-50 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 md:-mx-8 md:px-6"
    >
      {error && <p id="message-body-error" role="alert" className="mb-2 text-sm text-red-700">{error}</p>}
      <div className="flex items-end gap-2">
        <label htmlFor="message-body" className="sr-only">Mensagem</label>
        <textarea
          id="message-body"
          ref={fieldRef}
          rows={1}
          value={body}
          placeholder="Escreva uma mensagem"
          onChange={(event) => {
            setBody(event.target.value)
            if (validationError) setValidationError(null)
          }}
          onKeyDown={onKeyDown}
          maxLength={MESSAGE_MAX_LENGTH}
          aria-invalid={Boolean(error)}
          aria-describedby={[error ? 'message-body-error' : '', nearLimit ? 'message-body-count' : ''].filter(Boolean).join(' ') || undefined}
          className="min-h-11 flex-1 resize-none rounded-3xl border border-slate-300 bg-white px-4 py-2.5 text-base outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-teal-600"
        />
        <button
          type="submit"
          aria-label="Enviar"
          disabled={!trimmed || send.isPending}
          aria-busy={send.isPending}
          className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-teal-700 text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Icon name="send" className="h-5 w-5" />
        </button>
      </div>
      {nearLimit && (
        <p id="message-body-count" className="mt-1 text-right text-sm text-slate-600">{body.length}/{MESSAGE_MAX_LENGTH}</p>
      )}
    </form>
  )
}
