import { api } from '../lib/apiClient'
import type { ClinicalHistoryCreateRequest, ClinicalHistoryEntry, ClinicalHistoryUpdateRequest } from '../types/api'

const entry = (id: string) => `/api/v1/clinical-history/${encodeURIComponent(id)}`

/** Clinical history entries. The backend decides origin, confirmation and who may do what. */
export const clinicalHistoryService = {
  list: (patientId: string, signal?: AbortSignal) =>
    api.get<ClinicalHistoryEntry[]>(`/api/v1/patients/${encodeURIComponent(patientId)}/clinical-history`, signal),
  create: (patientId: string, payload: ClinicalHistoryCreateRequest) =>
    api.post<ClinicalHistoryEntry>(`/api/v1/patients/${encodeURIComponent(patientId)}/clinical-history`, payload),
  update: (id: string, payload: ClinicalHistoryUpdateRequest) => api.patch<ClinicalHistoryEntry>(entry(id), payload),
  confirm: (id: string, version: number) => api.post<ClinicalHistoryEntry>(`${entry(id)}/confirm`, { expected_version: version }),
  hide: (id: string, version: number, reason: string) =>
    api.post<ClinicalHistoryEntry>(`${entry(id)}/hide`, { expected_version: version, reason }),
  show: (id: string, version: number) => api.post<ClinicalHistoryEntry>(`${entry(id)}/show`, { expected_version: version }),
  remove: (id: string, version: number, reason?: string) =>
    api.post<ClinicalHistoryEntry>(`${entry(id)}/delete`, { expected_version: version, ...(reason ? { reason } : {}) }),
}
