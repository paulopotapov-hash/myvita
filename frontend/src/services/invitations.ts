import { api } from '../lib/apiClient'
import type {
  InvitationAcceptRequest,
  InvitationCreated,
  InvitationPreview,
  InvitationPublic,
  PatientInvitationRequest,
  StaffInvitationRequest,
  UserPublic,
} from '../types/api'

export const invitationsService = {
  preview: (token: string, signal?: AbortSignal) =>
    api.post<InvitationPreview>('/api/v1/invitations/preview', { token }, signal),
  accept: (payload: InvitationAcceptRequest) =>
    api.post<UserPublic>('/api/v1/invitations/accept', payload),
  inviteStaff: (payload: StaffInvitationRequest) =>
    api.post<InvitationCreated>('/api/v1/invitations/staff', payload),
  /** Clinic and patient identity are decided by the backend from the session. */
  invitePatient: (payload: PatientInvitationRequest) =>
    api.post<InvitationCreated>('/api/v1/invitations/patients', payload),
  /** Pending invitations of the caller's clinic; never includes tokens. */
  listPending: (page: number, pageSize: number, signal?: AbortSignal) =>
    api.getPage<InvitationPublic>(`/api/v1/invitations?page=${page}&page_size=${pageSize}`, signal),
  revoke: (invitationId: string) =>
    api.post<InvitationPublic>(`/api/v1/invitations/${encodeURIComponent(invitationId)}/revoke`),
}
