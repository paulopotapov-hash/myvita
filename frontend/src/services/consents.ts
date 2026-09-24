import { api } from '../lib/apiClient'
import type { ConsentCreateRequest, ConsentPublic } from '../types/api'

export const consentsService = {
  listForPatient: (patientId: string, signal?: AbortSignal) =>
    api.get<ConsentPublic[]>(`/api/v1/patients/${patientId}/consents`, signal),
  detail: (consentId: string, signal?: AbortSignal) =>
    api.get<ConsentPublic>(`/api/v1/consents/${consentId}`, signal),
  grant: (patientId: string, payload: ConsentCreateRequest) =>
    api.post<ConsentPublic>(`/api/v1/patients/${patientId}/consents`, payload),
  revoke: (consentId: string) => api.post<ConsentPublic>(`/api/v1/consents/${consentId}/revoke`),
}
