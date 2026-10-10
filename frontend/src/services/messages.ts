import { api, apiRequest } from '../lib/apiClient'
import type { ConversationCreateRequest, ConversationDetail, ConversationPublic, ConversationStatus, MessagePublic } from '../types/api'

export interface ConversationPage {
  conversation: ConversationDetail
  /** Total messages in the conversation (X-Total-Count). */
  total: number
}

export interface ConversationFilters {
  status?: ConversationStatus
  /** Staff only: conversations waiting for a doctor's review. */
  needsReview?: boolean
}

/** Participant and clinic checks live entirely in the backend; every call
 * here may 404 for a conversation the user is not part of. */
export const messagesService = {
  list: (page: number, pageSize: number, filters: ConversationFilters = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (filters.status) query.set('status', filters.status)
    if (filters.needsReview) query.set('needs_review', 'true')
    return api.getPage<ConversationPublic>(`/api/v1/conversations?${query}`, signal)
  },
  detail: async (conversationId: string, page: number, pageSize: number, signal?: AbortSignal): Promise<ConversationPage> => {
    let total = 0
    const conversation = await apiRequest<ConversationDetail>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}?page=${page}&page_size=${pageSize}`,
      {
        method: 'GET',
        signal,
        onResponse: (response) => {
          total = Number(response.headers.get('X-Total-Count') ?? 0)
        },
      },
    )
    return { conversation, total }
  },
  create: (payload: ConversationCreateRequest) => api.post<ConversationPublic>('/api/v1/conversations', payload),
  send: (conversationId: string, body: string) =>
    api.post<MessagePublic>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`, { body }),
  /** Nurses: open/waiting states. Doctors: also close and reopen. */
  setStatus: (conversationId: string, status: ConversationStatus) =>
    api.post<ConversationPublic>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/status`, { status }),
  /** Nurses ask the care team's doctors to review. */
  escalate: (conversationId: string) =>
    api.post<ConversationPublic>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/escalate`),
  markRead: (conversationId: string) =>
    api.post<{ updated_count: number }>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/read`),
}
