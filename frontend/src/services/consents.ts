import { api } from '../lib/apiClient'
import type { ConsentCreateRequest, ConsentPublic } from '../types/api'

export const consentsService = {
  listForPatient: (patientId: string, signal?: AbortSignal) =>
    api.get<ConsentPublic[]>(`/api/v1/patients/${patientId}/consents`, signal),
  grant: (patientId: string, payload: ConsentCreateRequest) =>
    api.post<ConsentPublic>(`/api/v1/patients/${patientId}/consents`, payload),
  revoke: (consentId: string) => api.post<ConsentPublic>(`/api/v1/consents/${consentId}/revoke`),
}
