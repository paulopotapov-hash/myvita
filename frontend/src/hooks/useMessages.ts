import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiClient'
import { messagesService } from '../services/messages'
import type { ConversationFilters } from '../services/messages'
import { patientsService } from '../services/patients'
import type { ConversationCreateRequest, ConversationStatus } from '../types/api'

export const CONVERSATIONS_KEY = ['conversations'] as const
export const MESSAGE_PAGE_SIZE = 30

export function useConversations(page: number, pageSize: number, enabled = true, filters: ConversationFilters = {}) {
  return useQuery({
    queryKey: [...CONVERSATIONS_KEY, 'list', page, pageSize, filters.status ?? null, Boolean(filters.needsReview)],
    queryFn: ({ signal }) => messagesService.list(page, pageSize, filters, signal),
    enabled,
  })
}

/** Backend pages are newest-first; each further page loads older history. */
export function useConversationMessages(conversationId: string) {
  return useInfiniteQuery({
    queryKey: [...CONVERSATIONS_KEY, 'detail', conversationId],
    queryFn: ({ pageParam, signal }) => messagesService.detail(conversationId, pageParam, MESSAGE_PAGE_SIZE, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage, pages) =>
      pages.length * MESSAGE_PAGE_SIZE < lastPage.total ? pages.length + 1 : undefined,
    enabled: Boolean(conversationId),
    // A 403/404 means "not yours or gone" — retrying won't change that.
    retry: false,
  })
}

export function useSendMessage(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: string) => messagesService.send(conversationId, body),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'list'] }),
        client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'detail', conversationId] }),
      ]),
    // A 403 means the thread became read-only meanwhile: refresh so `can_reply` updates.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 403) {
        void client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'detail', conversationId] })
        void client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'list'] })
      }
    },
  })
}

export function useMarkConversationRead(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => messagesService.markRead(conversationId),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'list'] }),
        client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'detail', conversationId] }),
      ]),
  })
}

function useRefreshConversation(conversationId: string) {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'list'] }),
      client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'detail', conversationId] }),
    ])
}

export function useSetConversationStatus(conversationId: string) {
  const refresh = useRefreshConversation(conversationId)
  return useMutation({
    mutationFn: (status: ConversationStatus) => messagesService.setStatus(conversationId, status),
    onSuccess: refresh,
  })
}

export function useEscalateConversation(conversationId: string) {
  const refresh = useRefreshConversation(conversationId)
  return useMutation({ mutationFn: () => messagesService.escalate(conversationId), onSuccess: refresh })
}

export function useCreateConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConversationCreateRequest) => messagesService.create(payload),
    onSuccess: () => client.invalidateQueries({ queryKey: [...CONVERSATIONS_KEY, 'list'] }),
  })
}

/** Staff: patients of their clinic matching a search term (existing patients endpoint). */
export function usePatientContactSearch(search: string) {
  return useQuery({
    queryKey: [...CONVERSATIONS_KEY, 'contacts', 'patients', search],
    queryFn: ({ signal }) => patientsService.search(search, 1, 10, signal),
    enabled: search.trim().length > 0,
  })
}

/** Page size used to count conversations with unread messages (the backend's maximum page). */
export const UNREAD_CONVERSATIONS_SCAN = 100

/**
 * Number of CONVERSATIONS with unread messages (not the number of messages), for
 * menu badges. The API has no aggregate count, so this counts within the
 * UNREAD_CONVERSATIONS_SCAN most recently active conversations.
 */
export function useUnreadConversationsCount(enabled: boolean) {
  const query = useConversations(1, UNREAD_CONVERSATIONS_SCAN, enabled)
  return query.data?.items.filter((conversation) => conversation.unread_count > 0).length ?? 0
}
