import { api } from '../lib/apiClient'
import type { MyPhoto, PatientPhotoStaff } from '../types/patientPhotos'

const BASE = '/api/v1/patient-photos'

/** Same-origin, cookie-authenticated, never cached: the server checks access on every load. */
export function photoImageUrl(photoId: string): string {
  return `${BASE}/${encodeURIComponent(photoId)}/image`
}

export const patientPhotosService = {
  mine: (signal?: AbortSignal) => api.get<MyPhoto>(`${BASE}/mine`, signal),
  /** The cropped photo (JPEG); the server checks, strips metadata and resizes it. */
  upload: (photo: Blob) => {
    const form = new FormData()
    form.append('file', photo, 'foto.jpg')
    return api.postForm<MyPhoto>(BASE, form)
  },
  remove: (photoId: string) => api.post<MyPhoto>(`${BASE}/${encodeURIComponent(photoId)}/remove`),
  forPatient: (patientId: string, signal?: AbortSignal) =>
    api.get<PatientPhotoStaff>(`${BASE}/patients/${encodeURIComponent(patientId)}`, signal),
  approve: (photoId: string) => api.post<PatientPhotoStaff>(`${BASE}/${encodeURIComponent(photoId)}/approve`),
  reject: (photoId: string, reason: string) =>
    api.post<PatientPhotoStaff>(`${BASE}/${encodeURIComponent(photoId)}/reject`, { reason }),
  pendingCount: (signal?: AbortSignal) => api.get<{ count: number }>(`${BASE}/pending-count`, signal),
}
