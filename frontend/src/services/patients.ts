import { api } from '../lib/apiClient'
import type { PatientPublic, PatientRegisterRequest, PatientUpdateRequest } from '../types/api'

export const patientsService = {
  register: (payload: PatientRegisterRequest) => api.post<PatientPublic>('/api/v1/patients/register', payload),
  /** Staff/clinic_admin only — the backend enforces this with a 403 for
   * patients; the frontend never needs to duplicate that check to be
   * correct, only to decide whether it's worth calling at all. */
  list: (signal?: AbortSignal) => api.get<PatientPublic[]>('/api/v1/patients', signal),
  listPage: (page: number, pageSize: number, signal?: AbortSignal) =>
    api.getPage<PatientPublic>(`/api/v1/patients?page=${page}&page_size=${pageSize}`, signal),
  detail: (patientId: string, signal?: AbortSignal) =>
    api.get<PatientPublic>(`/api/v1/patients/${patientId}`, signal),
  update: (patientId: string, payload: PatientUpdateRequest) =>
    api.patch<PatientPublic>(`/api/v1/patients/${patientId}`, payload),
}
