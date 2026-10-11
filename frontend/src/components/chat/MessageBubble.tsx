import { chatTime } from '../../lib/chatFormat'
import { SENDER_ROLE_LABELS } from '../../lib/messaging'
import type { MessagePublic } from '../../types/api'
import { Avatar } from '../Avatar'
import { Icon } from '../Icon'

/**
 * One chat bubble: mine on the right in the brand colour, the team's on the left
 * in light grey with a small avatar. Time sits inside the bubble; on my messages
 * ✓ means sent and ✓✓ means read by the other side.
 */
export function MessageBubble({ message, showSender, showAvatar }: {
  message: MessagePublic
  /** First message of a run from the same person: show their name. */
  showSender: boolean
  /** Last message of a run from the same person: show their avatar. */
  showAvatar: boolean
}) {
  const own = message.is_mine
  const author = `${message.sender_name} · ${SENDER_ROLE_LABELS[message.sender_role]}`
  return (
    <li className={`flex items-end gap-2 ${own ? 'justify-end' : 'justify-start'}`}>
      {!own && (showAvatar ? <Avatar name={message.sender_name} size="sm" /> : <span className="w-8 shrink-0" aria-hidden="true" />)}
      <article
        aria-label={own ? 'Mensagem enviada por si' : `Mensagem de ${author}`}
        className={`min-w-0 max-w-[80%] rounded-2xl px-3 pb-1.5 pt-2 shadow-sm ${
          own ? 'rounded-br-md bg-teal-700 text-white' : 'rounded-bl-md bg-slate-200 text-slate-900'
        }`}
      >
        {!own && showSender && <p className="text-sm font-semibold text-teal-800">{author}</p>}
        <p className="whitespace-pre-wrap break-words text-base">{message.body}</p>
        <p className={`mt-0.5 flex items-center justify-end gap-1 text-xs ${own ? 'text-teal-50' : 'text-slate-700'}`}>
          <time dateTime={message.created_at}>{chatTime(message.created_at)}</time>
          {own && (
            <>
              <Icon name={message.read_at ? 'ticks' : 'tick'} className="h-4 w-4" strokeWidth={2} />
              <span className="sr-only">{message.read_at ? 'Lida' : 'Enviada'}</span>
            </>
          )}
        </p>
      </article>
    </li>
  )
}
