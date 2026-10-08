import { api, apiRequest } from '../lib/apiClient'
import type { ConversationCreateRequest, ConversationDetail, ConversationPublic, MessagePublic } from '../types/api'

export interface ConversationPage {
  conversation: ConversationDetail
  /** Total messages in the conversation (X-Total-Count). */
  total: number
}

/** Participant and clinic checks live entirely in the backend; every call
 * here may 404 for a conversation the user is not part of. */
export const messagesService = {
  list: (page: number, pageSize: number, signal?: AbortSignal) =>
    api.getPage<ConversationPublic>(`/api/v1/conversations?page=${page}&page_size=${pageSize}`, signal),
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
  markRead: (conversationId: string) =>
    api.post<{ updated_count: number }>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/read`),
}
