import { api } from '../lib/apiClient'
import type { StaffCreateRequest, StaffPublic } from '../types/api'

export const staffService = {
  create: (payload: StaffCreateRequest) => api.post<StaffPublic>('/api/v1/staff', payload),
  list: (signal?: AbortSignal) => api.get<StaffPublic[]>('/api/v1/staff', signal),
}
