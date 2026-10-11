import { Link } from 'react-router-dom'
import { listTime } from '../../lib/chatFormat'
import { patientStatusLabel } from '../../lib/messaging'
import { badgeText } from '../../lib/navItems'
import type { ConversationPublic } from '../../types/api'
import { Avatar } from '../Avatar'

/**
 * One row of the patient's conversation list: initials, name, relative time
 * and an unread indicator. Conversations with unread messages are in bold.
 * (The API does not return the last message, so no preview is shown.)
 */
export function ConversationListItem({ conversation, to }: { conversation: ConversationPublic; to: string }) {
  const unread = conversation.unread_count
  const hasUnread = unread > 0
  return (
    <li>
      <Link to={to} className="flex min-h-[4.5rem] items-center gap-3 rounded-xl px-3 py-3 hover:bg-white">
        <Avatar name={conversation.staff_name} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className={`truncate text-base ${hasUnread ? 'font-bold text-slate-900' : 'font-medium text-slate-800'}`}>{conversation.staff_name}</p>
            <time
              dateTime={conversation.updated_at}
              className={`shrink-0 text-sm ${hasUnread ? 'font-semibold text-teal-800' : 'text-slate-600'}`}
            >
              {listTime(conversation.updated_at)}
            </time>
          </div>
          <div className="mt-0.5 flex items-center justify-between gap-2">
            <p className={`truncate text-base ${hasUnread ? 'font-semibold text-slate-900' : 'text-slate-600'}`}>
              {hasUnread ? (unread === 1 ? '1 mensagem nova' : `${unread} mensagens novas`) : `Equipa clínica · ${patientStatusLabel(conversation.status)}`}
            </p>
            {hasUnread && (
              <span className="inline-flex min-w-6 shrink-0 items-center justify-center rounded-full bg-teal-700 px-1.5 py-0.5 text-sm font-semibold text-white" aria-hidden="true">
                {badgeText(unread)}
              </span>
            )}
          </div>
        </div>
      </Link>
    </li>
  )
}
