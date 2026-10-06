import { api } from '../lib/apiClient'
import type { LoginRequest, UserPublic } from '../types/api'

export const authService = {
  login: (payload: LoginRequest) => api.post<UserPublic>('/api/v1/auth/login', payload),
  logout: () => api.post<void>('/api/v1/auth/logout'),
  me: (signal?: AbortSignal) => api.get<UserPublic>('/api/v1/auth/me', signal),
}
