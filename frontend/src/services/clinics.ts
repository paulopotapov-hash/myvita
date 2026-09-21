import { api } from '../lib/apiClient'
import type { ClinicOnboardingRequest, ClinicPublic, ClinicSummary } from '../types/api'

export const clinicsService = {
  onboard: (payload: ClinicOnboardingRequest) => api.post<ClinicPublic>('/api/v1/clinics', payload),
  list: (signal?: AbortSignal) => api.get<ClinicSummary[]>('/api/v1/clinics', signal),
}
