import { api } from '../lib/apiClient'
import type {
  MedicationCreateRequest,
  MedicationDeactivateRequest,
  MedicationPublic,
  MedicationUpdateRequest,
} from '../types/api'

/** The backend caps a page at 100 rows; the section warns when `total` exceeds it. */
export const MEDICATIONS_PAGE_SIZE = 100

export const medicationsService = {
  list: (patientId: string, signal?: AbortSignal) =>
    api.getPage<MedicationPublic>(`/api/v1/patients/${patientId}/medications?page_size=${MEDICATIONS_PAGE_SIZE}`, signal),
  detail: (medicationId: string, signal?: AbortSignal) => api.get<MedicationPublic>(`/api/v1/medications/${medicationId}`, signal),
  create: (patientId: string, payload: MedicationCreateRequest) => api.post<MedicationPublic>(`/api/v1/patients/${patientId}/medications`, payload),
  update: (medicationId: string, payload: MedicationUpdateRequest) => api.patch<MedicationPublic>(`/api/v1/medications/${medicationId}`, payload),
  deactivate: (medicationId: string, payload?: MedicationDeactivateRequest) =>
    api.post<MedicationPublic>(`/api/v1/medications/${medicationId}/deactivate`, payload),
}
