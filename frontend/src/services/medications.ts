import { api } from '../lib/apiClient'
import type {
  MedicationCreateRequest,
  MedicationDeactivateRequest,
  MedicationPublic,
  MedicationUpdateRequest,
  MedicationView,
} from '../types/api'

/** The backend caps a page at 100 rows; the section warns when `total` exceeds it. */
export const MEDICATIONS_PAGE_SIZE = 100

export const medicationsService = {
  list: (patientId: string, signal?: AbortSignal) =>
    api.getPage<MedicationView>(`/api/v1/patients/${patientId}/medications?page_size=${MEDICATIONS_PAGE_SIZE}`, signal),
  detail: (medicationId: string, signal?: AbortSignal) => api.get<MedicationView>(`/api/v1/medications/${medicationId}`, signal),
  /** A professional's prescription, or the patient's own declaration (the backend decides by role). */
  create: (patientId: string, payload: MedicationCreateRequest) => api.post<MedicationView>(`/api/v1/patients/${patientId}/medications`, payload),
  update: (medicationId: string, payload: MedicationUpdateRequest) => api.patch<MedicationView>(`/api/v1/medications/${medicationId}`, payload),
  deactivate: (medicationId: string, payload?: MedicationDeactivateRequest) =>
    api.post<MedicationPublic>(`/api/v1/medications/${medicationId}/deactivate`, payload),
  /** Confirms a declaration; the professional may complete the dose and the (full) start date. */
  confirm: (medicationId: string, completion: { dosage?: string; start_date?: string } = {}) =>
    api.post<MedicationPublic>(`/api/v1/medications/${medicationId}/confirm`, completion),
  hide: (medicationId: string, reason: string) => api.post<MedicationPublic>(`/api/v1/medications/${medicationId}/hide`, { reason }),
  show: (medicationId: string) => api.post<MedicationPublic>(`/api/v1/medications/${medicationId}/show`),
  remove: (medicationId: string, reason?: string) =>
    api.post<MedicationView>(`/api/v1/medications/${medicationId}/delete`, reason ? { reason } : {}),
}
