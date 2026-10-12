import { api } from '../lib/apiClient'
import type { AppointmentPatientView } from '../types/api'
import type {
  Absence,
  AbsenceKind,
  Agenda,
  BookableProfessional,
  BookingRequest,
  AppointmentTypeOption,
  BookingMode,
  BookingSettings,
  BookingSettingsOut,
  Professional,
  ScheduleRule,
  Slot,
  Specialty,
} from '../types/scheduling'

const BASE = '/api/v1/scheduling'
const q = (params: Record<string, string | undefined>) =>
  new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1]))).toString()

export const schedulingService = {
  specialties: (signal?: AbortSignal) => api.get<Specialty[]>(`${BASE}/specialties`, signal),
  createSpecialty: (name: string) => api.post<Specialty>(`${BASE}/specialties`, { name }),
  updateSpecialty: (id: string, payload: Partial<Pick<Specialty, 'name' | 'active'>>) =>
    api.patch<Specialty>(`${BASE}/specialties/${encodeURIComponent(id)}`, payload),

  types: (signal?: AbortSignal) => api.get<AppointmentTypeOption[]>(`${BASE}/appointment-types`, signal),
  createType: (payload: { name: string; duration_minutes: number; specialty_id: string; booking_mode: BookingMode }) =>
    api.post<AppointmentTypeOption>(`${BASE}/appointment-types`, payload),
  updateType: (id: string, payload: Partial<Omit<AppointmentTypeOption, 'id'>>) =>
    api.patch<AppointmentTypeOption>(`${BASE}/appointment-types/${encodeURIComponent(id)}`, payload),

  settings: (signal?: AbortSignal) => api.get<BookingSettingsOut>(`${BASE}/settings`, signal),
  updateSettings: (payload: BookingSettings) => api.patch<BookingSettingsOut>(`${BASE}/settings`, payload),

  professionals: (signal?: AbortSignal) => api.get<Professional[]>(`${BASE}/professionals`, signal),
  updateProfessional: (id: string, payload: { specialty_id?: string | null; accepts_new_patients?: boolean }) =>
    api.patch<Professional>(`${BASE}/professionals/${encodeURIComponent(id)}`, payload),
  schedule: (staffId: string, signal?: AbortSignal) =>
    api.get<ScheduleRule[]>(`${BASE}/professionals/${encodeURIComponent(staffId)}/schedule`, signal),
  replaceSchedule: (staffId: string, rules: ScheduleRule[]) =>
    api.post<ScheduleRule[]>(`${BASE}/professionals/${encodeURIComponent(staffId)}/schedule`, { rules }),

  addAbsence: (payload: { starts_at: string; ends_at: string; kind: AbsenceKind }, staffId?: string) =>
    api.post<Absence>(`${BASE}/absences${staffId ? `?${q({ staff_id: staffId })}` : ''}`, payload),
  deleteAbsence: (id: string) => api.post<void>(`${BASE}/absences/${encodeURIComponent(id)}/delete`),
  agenda: (from: string, to: string, staffId?: string, signal?: AbortSignal) =>
    api.get<Agenda>(`${BASE}/agenda?${q({ from, to, staff_id: staffId })}`, signal),

  bookableProfessionals: (typeId: string, signal?: AbortSignal) =>
    api.get<BookableProfessional[]>(`${BASE}/bookable-professionals?${q({ appointment_type_id: typeId })}`, signal),
  /** The patient's own booking; the server re-checks the slot and answers 409 if it was taken. */
  book: (payload: BookingRequest) => api.post<AppointmentPatientView>(`${BASE}/bookings`, payload),

  slots: (typeId: string, from: string, to: string, staffId?: string, signal?: AbortSignal) =>
    api.get<Slot[]>(`${BASE}/slots?${q({ appointment_type_id: typeId, from, to, staff_id: staffId })}`, signal),

  /** The patient's own appointment: cancel (before the clinic's deadline) or move to a free slot. */
  cancelBooking: (appointmentId: string) =>
    api.post<AppointmentPatientView>(`${BASE}/bookings/${encodeURIComponent(appointmentId)}/cancel`),
  rescheduleSlots: (appointmentId: string, from: string, to: string, professional: 'same' | 'any', signal?: AbortSignal) =>
    api.get<Slot[]>(`${BASE}/bookings/${encodeURIComponent(appointmentId)}/slots?${q({ from, to, professional })}`, signal),
  /** The patient confirms they will come (idempotent). */
  confirmBooking: (appointmentId: string) =>
    api.post<AppointmentPatientView>(`${BASE}/bookings/${encodeURIComponent(appointmentId)}/confirm`),
  /** Returns the new appointment; 409 (nothing changed) if the slot was taken meanwhile. */
  reschedule: (appointmentId: string, payload: { starts_at: string; staff_id?: string }) =>
    api.post<AppointmentPatientView>(`${BASE}/bookings/${encodeURIComponent(appointmentId)}/reschedule`, payload),
}
