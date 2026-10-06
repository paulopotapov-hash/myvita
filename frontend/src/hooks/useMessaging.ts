import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { messagingService } from '../services/messaging'
import type { ConversationStatus } from '../types/api'

export function useConversationInbox(enabled = true) {
  return useQuery({
    queryKey: ['messages', 'inbox'],
    queryFn: ({ signal }) => messagingService.inbox(signal),
    enabled,
  })
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: ['messages', 'conversation', id],
    queryFn: ({ signal }) => messagingService.conversation(id, signal),
    enabled: Boolean(id),
  })
}

function useRefreshConversationQueries() {
  const client = useQueryClient()
  return (id?: string) => {
    void client.invalidateQueries({ queryKey: ['messages', 'inbox'] })
    if (id) void client.invalidateQueries({ queryKey: ['messages', 'conversation', id] })
  }
}

export function useStartConversation() {
  const refresh = useRefreshConversationQueries()
  return useMutation({
    mutationFn: ({ patientId, subject, body }: { patientId: string; subject: string; body: string }) =>
      messagingService.start(patientId, { subject, body }),
    onSuccess: (conversation) => refresh(conversation.id),
  })
}

export function useReplyToConversation() {
  const refresh = useRefreshConversationQueries()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => messagingService.reply(id, body),
    onSuccess: (conversation) => refresh(conversation.id),
  })
}

export function useUpdateConversationStatus() {
  const refresh = useRefreshConversationQueries()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ConversationStatus }) => messagingService.setStatus(id, status),
    onSuccess: (conversation) => refresh(conversation.id),
  })
}

export function useEscalateConversation() {
  const refresh = useRefreshConversationQueries()
  return useMutation({
    mutationFn: (id: string) => messagingService.escalate(id),
    onSuccess: (conversation) => refresh(conversation.id),
  })
}
