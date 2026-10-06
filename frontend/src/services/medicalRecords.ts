import { api } from '../lib/apiClient'
import type { MedicalRecordPublic, MedicalRecordRevisionPublic, MedicalRecordWriteRequest } from '../types/api'

export const medicalRecordsService = {
  list: (patientId: string, signal?: AbortSignal) => api.get<MedicalRecordPublic[]>(`/api/v1/patients/${patientId}/medical-records`, signal),
  detail: (recordId: string, signal?: AbortSignal) => api.get<MedicalRecordPublic>(`/api/v1/medical-records/${recordId}`, signal),
  create: (patientId: string, payload: MedicalRecordWriteRequest) => api.post<MedicalRecordPublic>(`/api/v1/patients/${patientId}/medical-records`, payload),
  update: (recordId: string, payload: MedicalRecordWriteRequest) => api.patch<MedicalRecordPublic>(`/api/v1/medical-records/${recordId}`, payload),
  revisions: (recordId: string, signal?: AbortSignal) => api.get<MedicalRecordRevisionPublic[]>(`/api/v1/medical-records/${recordId}/revisions`, signal),
}
