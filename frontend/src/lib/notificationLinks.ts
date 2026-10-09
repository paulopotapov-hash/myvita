import { messagesBasePath, NEW_MESSAGE_NOTIFICATION_TITLE } from './messaging'
import type { NotificationPublic, UserPublic } from '../types/api'

/**
 * Deep link for a notification, from its target (decisions M6/D4). The target
 * page re-checks access on open, so a stale or foreign target only yields the
 * page's own "not found" state.
 */
export function notificationLink(
  notification: NotificationPublic,
  user: Pick<UserPublic, 'role'> | null,
): { to: string; label: string } {
  if (user && notification.target_type === 'conversation' && notification.conversation_target_id) {
    return { to: `${messagesBasePath(user)}/${encodeURIComponent(notification.conversation_target_id)}`, label: 'Abrir conversa' }
  }
  if (user?.role === 'patient' && notification.target_type === 'document' && notification.target_id) {
    return { to: `/patient/documentos?document=${encodeURIComponent(notification.target_id)}`, label: 'Abrir documento' }
  }
  // Message notifications created before deep links existed.
  if (user && notification.title === NEW_MESSAGE_NOTIFICATION_TITLE) return { to: messagesBasePath(user), label: 'Abrir mensagens' }
  return { to: user?.role === 'patient' ? '/patient/consultas' : '/app/consultas', label: 'Abrir consultas' }
}
