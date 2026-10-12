import type { AppointmentRequestPublic, AppointmentRequestStatus } from '../types/api'
import { formatClinicDay, formatClinicTime, WEEKDAYS } from './clinicTime'

export const REQUEST_STATUS_LABELS: Record<AppointmentRequestStatus, string> = {
  pending: 'Pendente',
  proposed: 'Proposta da clínica',
  accepted: 'Aceite',
  rejected: 'Recusado',
  cancelled: 'Cancelado',
  declined: 'Proposta recusada',
}

export const OPEN_REQUEST_STATUSES: AppointmentRequestStatus[] = ['pending', 'proposed']

/** "YYYY-MM-DD" -> "12/10" (calendar date, no time zone involved). */
function shortDate(key: string): string {
  const [, month, day] = key.split('-')
  return `${day}/${month}`
}

type Preferences = Partial<
  Pick<AppointmentRequestPublic, 'preferred_start' | 'preferred_from' | 'preferred_to' | 'preferred_weekdays' | 'preferred_period'>
>

/** What the patient asked for, in one line: "De 12/10 a 19/10 · segunda, quarta · manhã". */
export function describePreferences(request: Preferences): string {
  if (request.preferred_start) {
    return `${formatClinicDay(request.preferred_start)}, ${formatClinicTime(request.preferred_start)}`
  }
  const parts: string[] = []
  if (request.preferred_from) {
    parts.push(request.preferred_to && request.preferred_to !== request.preferred_from
      ? `De ${shortDate(request.preferred_from)} a ${shortDate(request.preferred_to)}`
      : `A partir de ${shortDate(request.preferred_from)}`)
  }
  if (request.preferred_weekdays?.length) {
    parts.push(request.preferred_weekdays.map((day) => WEEKDAYS[day].toLowerCase()).join(', '))
  }
  if (request.preferred_period) parts.push(request.preferred_period === 'morning' ? 'manhã' : 'tarde')
  return parts.join(' · ')
}

/** "Consulta de rotina (Medicina Geral)" or a generic title. */
export function requestTitle(request: AppointmentRequestPublic): string {
  const kind = request.appointment_type ? `${request.appointment_type}${request.specialty ? ` (${request.specialty})` : ''}` : 'Pedido de consulta'
  return request.reschedule_of_id ? `Remarcação: ${kind}` : kind
}
