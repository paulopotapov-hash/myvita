import { api } from '../lib/apiClient'
import type { MedicalRecordCreateRequest, MedicalRecordPublic, MedicalRecordRevisionPublic, MedicalRecordUpdateRequest, MedicalRecordView } from '../types/api'

export const medicalRecordsService = {
  list: (patientId: string, signal?: AbortSignal) => api.get<MedicalRecordView[]>(`/api/v1/patients/${patientId}/medical-records`, signal),
  detail: (recordId: string, signal?: AbortSignal) => api.get<MedicalRecordView>(`/api/v1/medical-records/${recordId}`, signal),
  create: (patientId: string, payload: MedicalRecordCreateRequest) => api.post<MedicalRecordPublic>(`/api/v1/patients/${patientId}/medical-records`, payload),
  update: (recordId: string, payload: MedicalRecordUpdateRequest) => api.patch<MedicalRecordPublic>(`/api/v1/medical-records/${recordId}`, payload),
  /** Explicit decision to share the version the professional reviewed. */
  share: (recordId: string, expectedVersion: number) => api.post<MedicalRecordPublic>(`/api/v1/medical-records/${recordId}/share`, { expected_version: expectedVersion }),
  /** Withdraws patient access immediately. */
  unshare: (recordId: string) => api.post<MedicalRecordPublic>(`/api/v1/medical-records/${recordId}/unshare`),
  revisions: (recordId: string, signal?: AbortSignal) => api.get<MedicalRecordRevisionPublic[]>(`/api/v1/medical-records/${recordId}/revisions`, signal),
}
