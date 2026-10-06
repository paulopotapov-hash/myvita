import { api } from '../lib/apiClient'
import type {
  LoginRequest,
  MfaChallengeResponse,
  MfaRecoveryCodesResponse,
  MfaSetupResponse,
  PasswordChangeRequest,
  UserPublic,
} from '../types/api'

export const authService = {
  /** Resolves to the session user, or to an MFA challenge (HTTP 202) when a
   * second factor is still required — use `isMfaChallenge` to tell them apart. */
  login: (payload: LoginRequest) => api.post<UserPublic | MfaChallengeResponse>('/api/v1/auth/login', payload),
  verifyMfa: (code: string) => api.post<UserPublic>('/api/v1/auth/mfa/verify', { code }),
  logout: () => api.post<void>('/api/v1/auth/logout'),
  me: (signal?: AbortSignal) => api.get<UserPublic>('/api/v1/auth/me', signal),
  changePassword: (payload: PasswordChangeRequest) =>
    api.post<void>('/api/v1/auth/change-password', payload),
  startMfaSetup: () => api.post<MfaSetupResponse>('/api/v1/auth/mfa/setup'),
  enableMfa: (code: string) => api.post<MfaRecoveryCodesResponse>('/api/v1/auth/mfa/enable', { code }),
  requestPasswordReset: (email: string) =>
    api.post<{ detail: string }>('/api/v1/auth/password-reset/request', { email }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    api.post<void>('/api/v1/auth/password-reset/confirm', { token, new_password: newPassword }),
}
