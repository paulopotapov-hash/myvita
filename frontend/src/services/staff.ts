import { api } from '../lib/apiClient'
import type { StaffCreateRequest, StaffPublic, StaffRole } from '../types/api'

export const staffService = {
  create: (payload: StaffCreateRequest) => api.post<StaffPublic>('/api/v1/staff', payload),
  list: (signal?: AbortSignal) => api.get<StaffPublic[]>('/api/v1/staff', signal),
  activate: (staffId: string) => api.post<StaffPublic>(`/api/v1/staff/${staffId}/activate`),
  deactivate: (staffId: string) => api.post<StaffPublic>(`/api/v1/staff/${staffId}/deactivate`),
  updateRole: (staffId: string, staff_role: StaffRole, specialty?: string) =>
    api.patch<StaffPublic>(`/api/v1/staff/${staffId}/role`, { staff_role, specialty }),
}
