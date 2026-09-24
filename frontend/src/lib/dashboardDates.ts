export function startOfTodayIso(): string {
  const date = new Date()
  date.setHours(0, 0, 0, 0)
  return date.toISOString()
}

export function startOfTomorrowIso(): string {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  date.setHours(0, 0, 0, 0)
  return date.toISOString()
}

export function endOfTodayIso(): string {
  const date = new Date()
  date.setHours(23, 59, 59, 999)
  return date.toISOString()
}
