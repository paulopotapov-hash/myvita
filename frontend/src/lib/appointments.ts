import type { AppointmentPatientView, AppointmentView } from '../types/api'

const UPCOMING_STATUSES = new Set(['scheduled', 'confirmed'])

/** The earliest scheduled or confirmed appointment that has not started yet. */
export function nextAppointment(appointments: AppointmentView[], now: Date): AppointmentView | undefined {
  return appointments
    .filter((appointment) => UPCOMING_STATUSES.has(appointment.status) && new Date(appointment.scheduled_at) >= now)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))[0]
}

/** Still ahead: scheduled or confirmed, and not yet over. */
export function isUpcoming(appointment: AppointmentPatientView, now: Date): boolean {
  return UPCOMING_STATUSES.has(appointment.status) && new Date(appointment.ends_at ?? appointment.scheduled_at) > now
}
