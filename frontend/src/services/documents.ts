import { api } from '../lib/apiClient'
import type { DocumentPublic } from '../types/api'

/** Mirrors backend/app/modules/documents/router.py `_ALLOWED` and DOCUMENT_MAX_UPLOAD_BYTES default. */
export const DOCUMENT_ACCEPT = 'application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg'
export const DOCUMENT_ALLOWED_TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg'])
export const DOCUMENT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
/** Mirrors backend DOCUMENT_TITLE_MAX_LENGTH. */
export const DOCUMENT_TITLE_MAX_LENGTH = 200

/** Documents are append-only: there is deliberately no delete call. */
export const documentsService = {
  listForPatient: (patientId: string, page: number, pageSize: number, signal?: AbortSignal) =>
    api.getPage<DocumentPublic>(`/api/v1/patients/${encodeURIComponent(patientId)}/documents?page=${page}&page_size=${pageSize}`, signal),
  upload: (patientId: string, file: File, title: string) => {
    const form = new FormData()
    form.append('title', title)
    form.append('file', file, file.name)
    return api.postForm<DocumentPublic>(`/api/v1/patients/${encodeURIComponent(patientId)}/documents`, form)
  },
  download: (documentId: string) => api.getBlob(`/api/v1/documents/${encodeURIComponent(documentId)}/download`),
}
