import { api } from '../lib/apiClient'
import type {
  AppointmentRequestAccept,
  AppointmentRequestCreate,
  AppointmentRequestPublic,
  AppointmentRequestStatus,
} from '../types/api'

const BASE = '/api/v1/appointment-requests'

/** Scoping is server-side: patients get their own requests, staff their clinic's. */
export const appointmentRequestsService = {
  list: (page: number, pageSize: number, status?: AppointmentRequestStatus, signal?: AbortSignal) =>
    api.getPage<AppointmentRequestPublic>(
      `${BASE}?page=${page}&page_size=${pageSize}${status ? `&status=${status}` : ''}`,
      signal,
    ),
  create: (payload: AppointmentRequestCreate) => api.post<AppointmentRequestPublic>(BASE, payload),
  accept: (id: string, payload: AppointmentRequestAccept) =>
    api.post<AppointmentRequestPublic>(`${BASE}/${encodeURIComponent(id)}/accept`, payload),
  reject: (id: string) => api.post<AppointmentRequestPublic>(`${BASE}/${encodeURIComponent(id)}/reject`),
  cancel: (id: string) => api.post<AppointmentRequestPublic>(`${BASE}/${encodeURIComponent(id)}/cancel`),
}
