import { api } from '../lib/apiClient'
import type {
  PatientIdentification,
  PatientIdentifiers,
  PatientIdentifiersUpdateRequest,
  PatientPublic,
  PatientSummary,
  PatientUpdateRequest,
} from '../types/api'

export const patientsService = {
  /** Staff/clinic_admin only — the backend enforces this with a 403 for
   * patients; the frontend never needs to duplicate that check to be
   * correct, only to decide whether it's worth calling at all. */
  list: (signal?: AbortSignal) => api.get<PatientSummary[]>('/api/v1/patients', signal),
  listPage: (page: number, pageSize: number, signal?: AbortSignal) =>
    api.getPage<PatientSummary>(`/api/v1/patients?page=${page}&page_size=${pageSize}`, signal),
  search: (search: string, page: number, pageSize: number, signal?: AbortSignal) => {
    const params = new URLSearchParams({ search, page: String(page), page_size: String(pageSize) })
    return api.getPage<PatientSummary>(`/api/v1/patients?${params.toString()}`, signal)
  },
  detail: (patientId: string, signal?: AbortSignal) =>
    api.get<PatientPublic>(`/api/v1/patients/${patientId}`, signal),
  update: (patientId: string, payload: PatientUpdateRequest) =>
    api.patch<PatientPublic>(`/api/v1/patients/${patientId}`, payload),
  /** Name and masked identifiers (last three digits). */
  identification: (patientId: string, signal?: AbortSignal) =>
    api.get<PatientIdentification>(`/api/v1/patients/${encodeURIComponent(patientId)}/identification`, signal),
  /** Full identifiers. Every call is audited by the backend ("dados identificativos consultados"). */
  revealIdentifiers: (patientId: string) =>
    api.post<PatientIdentifiers>(`/api/v1/patients/${encodeURIComponent(patientId)}/identification/reveal`),
  updateIdentifiers: (patientId: string, payload: PatientIdentifiersUpdateRequest) =>
    api.patch<PatientIdentification>(`/api/v1/patients/${encodeURIComponent(patientId)}/identification`, payload),
}
