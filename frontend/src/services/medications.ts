import { api } from '../lib/apiClient'
import type { MedicationCreateRequest, MedicationPublic, MedicationUpdateRequest } from '../types/api'

export const medicationsService = {
  list: (patientId: string, signal?: AbortSignal) => api.get<MedicationPublic[]>(`/api/v1/patients/${patientId}/medications`, signal),
  detail: (medicationId: string, signal?: AbortSignal) => api.get<MedicationPublic>(`/api/v1/medications/${medicationId}`, signal),
  create: (patientId: string, payload: MedicationCreateRequest) => api.post<MedicationPublic>(`/api/v1/patients/${patientId}/medications`, payload),
  update: (medicationId: string, payload: MedicationUpdateRequest) => api.patch<MedicationPublic>(`/api/v1/medications/${medicationId}`, payload),
}
