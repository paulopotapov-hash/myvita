import { api } from '../lib/apiClient'
import type { StaffPublic } from '../types/api'

export const staffService = {
  list: (signal?: AbortSignal) => api.get<StaffPublic[]>('/api/v1/staff', signal),
}
