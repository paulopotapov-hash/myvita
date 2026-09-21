import { api } from '../lib/apiClient'
import type { AppointmentCreateRequest, AppointmentPublic } from '../types/api'

export const appointmentsService = {
  create: (payload: AppointmentCreateRequest) => api.post<AppointmentPublic>('/api/v1/appointments', payload),
  /** No client-side filtering by clinic/patient — the backend scopes this
   * entirely server-side based on the session (patients see only their
   * own; staff/admin see their clinic's). Passing a filter here would be
   * meaningless: the backend doesn't accept one, by design. */
  list: (signal?: AbortSignal) => api.get<AppointmentPublic[]>('/api/v1/appointments', signal),
}
