import { api } from '../lib/apiClient'
import type { AccountSummary, PasswordResetIssued } from '../types/api'

/** Clinic-admin account administration (backend/app/modules/users). */
export const usersService = {
  list: (signal?: AbortSignal) => api.getPage<AccountSummary>('/api/v1/users?page_size=100', signal),
  deactivate: (userId: string) => api.post<AccountSummary>(`/api/v1/users/${userId}/deactivate`),
  reactivate: (userId: string) => api.post<AccountSummary>(`/api/v1/users/${userId}/reactivate`),
  issuePasswordReset: (userId: string) => api.post<PasswordResetIssued>(`/api/v1/users/${userId}/password-reset`),
  requirePasswordChange: (userId: string) =>
    api.post<AccountSummary>(`/api/v1/users/${userId}/require-password-change`),
  resetMfa: (userId: string) => api.post<AccountSummary>(`/api/v1/users/${userId}/mfa/reset`),
}

/** The reset token travels in the URL fragment, which browsers never send to
 * a server — same approach as invitation links. */
export function passwordResetLink(token: string): string {
  return `${window.location.origin}/redefinir-palavra-passe#token=${encodeURIComponent(token)}`
}
