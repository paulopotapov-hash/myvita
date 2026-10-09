import type { ConversationPublic, UserPublic } from '../types/api'

/**
 * Mirrors the backend participant rule (app/modules/messages/service.py):
 * patients and clinical staff (doctor/nurse) can message; clinic admins
 * and admin-role staff cannot. Only used to decide what to show — the
 * backend remains the authority and rejects everyone else.
 */
export function canUseMessaging(user: Pick<UserPublic, 'role' | 'staff_role'> | null): boolean {
  if (!user) return false
  if (user.role === 'patient') return true
  return user.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
}

export function messagesBasePath(user: Pick<UserPublic, 'role'>): string {
  return user.role === 'patient' ? '/patient/mensagens' : '/app/mensagens'
}

export function otherParticipantName(conversation: ConversationPublic, user: Pick<UserPublic, 'role'>): string {
  return user.role === 'patient' ? conversation.staff_name : conversation.patient_name
}

/** Notification titles the messages backend produces (NEW_MESSAGE_NOTIFICATION_TITLE). */
export const NEW_MESSAGE_NOTIFICATION_TITLE = 'Nova mensagem'

/**
 * Shown when a thread's professional no longer has an active care assignment
 * (`can_reply === false`). Mirrors backend INACTIVE_CONVERSATION; the backend
 * rejects replies in that state, so this is not only a UI rule.
 */
export const INACTIVE_CONVERSATION_MESSAGE = 'Esta conversa já não está activa. Para continuar, contacte a clínica.'
