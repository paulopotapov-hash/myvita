// Scheduling API (backend/app/modules/scheduling/schemas.py). Times are ISO instants (UTC);
// the clinic's wall-clock time zone is Europe/Lisbon.

export type BookingMode = 'direct' | 'request'
export type AbsenceKind = 'vacation' | 'other'

export interface Specialty {
  id: string
  name: string
  active: boolean
}

export interface AppointmentTypeOption {
  id: string
  name: string
  duration_minutes: number
  specialty_id: string
  booking_mode: BookingMode
  active: boolean
}

export interface BookingSettings {
  cancellation_deadline_hours: number
  waitlist_offer_minutes: number
  reminder_hours_before: number
  booking_horizon_days: number
}

export interface BookingSettingsOut extends BookingSettings {
  clinic_phone: string | null
  clinic_address: string | null
}

export interface Professional {
  id: string
  full_name: string
  staff_role: string
  specialty_id: string | null
  accepts_new_patients: boolean
}

/** One weekly block: 0 = Monday ... 6 = Sunday, "HH:MM" wall-clock times in Lisbon. */
export interface ScheduleRule {
  id?: string
  weekday: number
  start_time: string
  end_time: string
  valid_from: string | null
  valid_until: string | null
  appointment_type_ids: string[]
}

export interface Absence {
  id: string
  staff_id: string
  starts_at: string
  ends_at: string
  kind: AbsenceKind
  conflicting_appointments: number
}

export interface Slot {
  starts_at: string
  ends_at: string
  staff_id: string
  staff_name: string
}

export interface AgendaAppointment {
  id: string
  scheduled_at: string
  ends_at: string
  status: string
  patient_name: string
  appointment_type: string
  /** The patient confirmed they will come (step 7). */
  patient_confirmed?: boolean
}

export interface BookableProfessional {
  id: string
  full_name: string
  /** The patient already had an appointment with them (listed first). */
  known: boolean
}

export interface BookingRequest {
  appointment_type_id: string
  /** Omitted: "Qualquer disponível". */
  staff_id?: string
  starts_at: string
  reason?: string
}

export interface Agenda {
  staff_id: string
  appointments: AgendaAppointment[]
  absences: Absence[]
  rules: ScheduleRule[]
}

/** Waiting list ("Fast Pass", step 6): earlier slots for one of the patient's appointments. */
export type WaitlistScope = 'professional' | 'specialty'

export interface WaitlistOffer {
  id: string
  starts_at: string
  ends_at: string
  staff_name: string
  expires_at: string
}

export interface WaitlistEntry {
  id: string
  appointment_id: string
  scope: WaitlistScope
  status: 'active' | 'fulfilled' | 'left' | 'closed'
  created_at: string
  offers: WaitlistOffer[]
}
