import { api } from '../lib/apiClient'
import type { InvitationAcceptRequest, InvitationCreated, InvitationPreview, StaffInvitationRequest, UserPublic } from '../types/api'

export const invitationsService = {
  preview: (token: string, signal?: AbortSignal) =>
    api.get<InvitationPreview>(`/api/v1/invitations/preview?token=${encodeURIComponent(token)}`, signal),
  accept: (payload: InvitationAcceptRequest) =>
    api.post<UserPublic>('/api/v1/invitations/accept', payload),
  inviteStaff: (payload: StaffInvitationRequest) =>
    api.post<InvitationCreated>('/api/v1/invitations/staff', payload),
}
