import { api } from '../lib/apiClient'
import type {
  AppointmentCreateRequest,
  AppointmentPublic,
  AppointmentStatus,
  AppointmentUpdateRequest,
} from '../types/api'

export interface AppointmentListFilters {
  limit?: number
  offset?: number
  patient_id?: string
  staff_id?: string
  status?: AppointmentStatus
  start_date?: string
  end_date?: string
}

function listPath(filters: AppointmentListFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value))
  }
  const query = params.toString()
  return `/api/v1/appointments${query ? `?${query}` : ''}`
}

export const appointmentsService = {
  create: (payload: AppointmentCreateRequest) => api.post<AppointmentPublic>('/api/v1/appointments', payload),
  detail: (id: string, signal?: AbortSignal) => api.get<AppointmentPublic>(`/api/v1/appointments/${id}`, signal),
  update: (id: string, payload: AppointmentUpdateRequest) =>
    api.patch<AppointmentPublic>(`/api/v1/appointments/${id}`, payload),
  cancel: (id: string) => api.post<AppointmentPublic>(`/api/v1/appointments/${id}/cancel`),
  /** Every filter only narrows the server-authorized result set. Tenant and
   * patient scoping remain entirely enforced by the backend session. */
  list: (filters: AppointmentListFilters = {}, signal?: AbortSignal) =>
    api.get<AppointmentPublic[]>(listPath(filters), signal),
}
