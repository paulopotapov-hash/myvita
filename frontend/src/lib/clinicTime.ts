/**
 * The clinic's wall clock is Europe/Lisbon, whatever the browser's own time zone is.
 * Instants travel as ISO strings (UTC); these helpers show them in Lisbon time and turn
 * a Lisbon wall-clock "YYYY-MM-DDTHH:MM" back into an instant, across DST changes.
 */

export const CLINIC_TIME_ZONE = 'Europe/Lisbon'

const partsFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: CLINIC_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})
const timeFormatter = new Intl.DateTimeFormat('pt-PT', { timeZone: CLINIC_TIME_ZONE, hour: '2-digit', minute: '2-digit' })
const dayFormatter = new Intl.DateTimeFormat('pt-PT', { timeZone: CLINIC_TIME_ZONE, weekday: 'long', day: 'numeric', month: 'long' })
const dateFormatter = new Intl.DateTimeFormat('pt-PT', { timeZone: CLINIC_TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric' })

function lisbonParts(instant: Date): Record<string, number> {
  const parts: Record<string, number> = {}
  for (const part of partsFormatter.formatToParts(instant)) {
    if (part.type !== 'literal') parts[part.type] = Number(part.value)
  }
  return parts
}

/** "YYYY-MM-DD" of the instant, in Lisbon. */
export function clinicDateKey(iso: string | Date): string {
  const parts = lisbonParts(typeof iso === 'string' ? new Date(iso) : iso)
  return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`
}

export function clinicToday(now: Date = new Date()): string {
  return clinicDateKey(now)
}

export function formatClinicTime(iso: string): string {
  return timeFormatter.format(new Date(iso))
}

export function formatClinicDay(iso: string): string {
  return dayFormatter.format(new Date(iso))
}

export function formatClinicDate(iso: string): string {
  return dateFormatter.format(new Date(iso))
}

/** Lisbon wall clock "YYYY-MM-DDTHH:MM" -> ISO instant (UTC). */
export function clinicLocalToIso(local: string): string {
  const [datePart, timePart = '00:00'] = local.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  const [hour, minute] = timePart.split(':').map(Number)
  const wanted = Date.UTC(year, month - 1, day, hour, minute)
  // Start from "as if UTC", then correct by Lisbon's offset at that instant (twice, for DST edges).
  let instant = wanted
  for (let i = 0; i < 2; i += 1) {
    const parts = lisbonParts(new Date(instant))
    const shown = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute)
    instant += wanted - shown
  }
  return new Date(instant).toISOString()
}

/** Calendar arithmetic on "YYYY-MM-DD" keys (no time zone involved). */
export function addDays(key: string, days: number): string {
  const [year, month, day] = key.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

/** Monday of the week that contains `key`. */
export function mondayOf(key: string): string {
  const [year, month, day] = key.split('-').map(Number)
  const weekday = (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7
  return addDays(key, -weekday)
}

export const WEEKDAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
