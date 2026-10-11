/**
 * Chat-style dates and times (patient messages), in the device's local time.
 * `now` is injectable for tests.
 */
const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const WEEKDAYS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/** Whole calendar days between `iso` and `now` (0 = today, 1 = yesterday). */
function daysAgo(iso: string, now: Date): number {
  return Math.round((startOfDay(now) - startOfDay(new Date(iso))) / 86_400_000)
}

/** "20:00" */
export function chatTime(iso: string): string {
  const date = new Date(iso)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

/** "9 out", or "9 out 2025" outside the current year. */
export function shortDate(iso: string, now = new Date()): string {
  const date = new Date(iso)
  const base = `${date.getDate()} ${MONTHS[date.getMonth()]}`
  return date.getFullYear() === now.getFullYear() ? base : `${base} ${date.getFullYear()}`
}

/** Separator between days in a conversation: "Hoje", "Ontem", "9 out". */
export function daySeparatorLabel(iso: string, now = new Date()): string {
  const days = daysAgo(iso, now)
  if (days === 0) return 'Hoje'
  if (days === 1) return 'Ontem'
  return shortDate(iso, now)
}

/** Grouping key for day separators. */
export function dayKey(iso: string): string {
  const date = new Date(iso)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

/** Conversation list time: "20:00" today, "Ontem", the weekday within a week, else "9 out". */
export function listTime(iso: string, now = new Date()): string {
  const days = daysAgo(iso, now)
  if (days <= 0) return chatTime(iso)
  if (days === 1) return 'Ontem'
  if (days < 7) return WEEKDAYS[new Date(iso).getDay()]
  return shortDate(iso, now)
}
