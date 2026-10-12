import { api } from '../lib/apiClient'
import type { AppointmentPatientView } from '../types/api'
import type { WaitlistEntry, WaitlistScope } from '../types/scheduling'

const BASE = '/api/v1/waitlist'

/** The patient's own waiting list; the server checks ownership, deadlines and offers. */
export const waitlistService = {
  list: (signal?: AbortSignal) => api.get<WaitlistEntry[]>(BASE, signal),
  join: (appointmentId: string, scope: WaitlistScope) => api.post<WaitlistEntry>(BASE, { appointment_id: appointmentId, scope }),
  leave: (entryId: string) => api.post<WaitlistEntry>(`${BASE}/${encodeURIComponent(entryId)}/leave`),
  /** Books the offered slot and cancels the old appointment; resolves to the new one (409 if gone). */
  accept: (offerId: string) => api.post<AppointmentPatientView>(`${BASE}/offers/${encodeURIComponent(offerId)}/accept`),
  decline: (offerId: string) => api.post<void>(`${BASE}/offers/${encodeURIComponent(offerId)}/decline`),
}
