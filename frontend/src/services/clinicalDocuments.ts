import { api, apiRequest } from '../lib/apiClient'
import type { ClinicalDocumentPublic, ClinicalDocumentVersionPublic } from '../types/api'

export const clinicalDocumentsService = {
  listForPatient: (patientId: string, signal?: AbortSignal) =>
    api.get<ClinicalDocumentPublic[]>(`/api/v1/patients/${patientId}/documents`, signal),
  listMine: (signal?: AbortSignal) => api.get<ClinicalDocumentPublic[]>('/api/v1/documents/mine', signal),
  createNote: (patientId: string, payload: { title: string; content: string }) =>
    api.post<ClinicalDocumentPublic>(`/api/v1/patients/${patientId}/documents/notes`, payload),
  uploadFile: (patientId: string, title: string, file: File) => {
    const body = new FormData()
    body.set('title', title)
    body.set('file', file)
    return apiRequest<ClinicalDocumentPublic>(`/api/v1/patients/${patientId}/documents/files`, { method: 'POST', body })
  },
  updateNote: (documentId: string, payload: { title: string; content: string }) =>
    api.patch<ClinicalDocumentPublic>(`/api/v1/documents/${documentId}/notes`, payload),
  history: (documentId: string, signal?: AbortSignal) =>
    api.get<ClinicalDocumentVersionPublic[]>(`/api/v1/documents/${documentId}/versions`, signal),
  version: (documentId: string, version: number, signal?: AbortSignal) =>
    api.get<ClinicalDocumentVersionPublic>(`/api/v1/documents/${documentId}/versions/${version}`, signal),
  download: async (documentId: string, version?: number) => {
    const path = version === undefined
      ? `/api/v1/documents/${documentId}/download`
      : `/api/v1/documents/${documentId}/versions/${version}/download`
    return api.getBlob(path)
  },
  uploadNewVersion: (documentId: string, title: string, file: File) => {
    const body = new FormData()
    body.set('title', title)
    body.set('file', file)
    return apiRequest<ClinicalDocumentPublic>(`/api/v1/documents/${documentId}/files/versions`, { method: 'POST', body })
  },
}
