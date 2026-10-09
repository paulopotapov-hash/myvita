import { api } from '../lib/apiClient'
import type { ClinicSummary } from '../types/api'

export const clinicsService = {
  list: (signal?: AbortSignal) => api.get<ClinicSummary[]>('/api/v1/clinics', signal),
  get: (clinicId: string, signal?: AbortSignal) => api.get<ClinicSummary>(`/api/v1/clinics/${encodeURIComponent(clinicId)}`, signal),
}
