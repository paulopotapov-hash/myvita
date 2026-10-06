import { api } from '../lib/apiClient'
import type { ConversationDetail, ConversationListItem, ConversationStatus } from '../types/api'

export const messagingService = {
  inbox: (signal?: AbortSignal) => api.get<ConversationListItem[]>('/api/v1/messages/inbox', signal),
  conversation: (id: string, signal?: AbortSignal) =>
    api.get<ConversationDetail>(`/api/v1/messages/conversations/${id}`, signal),
  start: (patientId: string, payload: { subject: string; body: string }) =>
    api.post<ConversationDetail>(`/api/v1/messages/patients/${patientId}/conversations`, payload),
  reply: (id: string, body: string) =>
    api.post<ConversationDetail>(`/api/v1/messages/conversations/${id}/messages`, { body }),
  setStatus: (id: string, status: ConversationStatus) =>
    api.patch<ConversationDetail>(`/api/v1/messages/conversations/${id}/status`, { status }),
  escalate: (id: string) => api.post<ConversationDetail>(`/api/v1/messages/conversations/${id}/escalation`, {}),
}
