import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/apiClient'
import { messagesService } from '../services/messages'
import { patientsService } from '../services/patients'
import type { ConversationCreateRequest } from '../types/api'

export const CONVERSATIONS_KEY = ['conversations'] as const
export const MESSAGE_PAGE_SIZE = 30

export function useConversations(page: number, pageSize: number, enabled = true) {
  return useQuery({
    queryKey: [...CONVERSATIONS_KEY, 'list', page, pageSize],
    queryFn: ({ signal }) => messagesService.list(page, pageSize, signal),
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
