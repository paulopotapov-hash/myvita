/**
 * Partial dates (decision D5): the API sends "2010", "2010-03" or "2010-03-12";
 * the UI shows "2010", "março 2010" or "12/03/2010".
 */

export type DatePrecision = 'year' | 'month' | 'day'

const MONTHS = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

export function precisionOf(value: string): DatePrecision {
  return value.length === 4 ? 'year' : value.length === 7 ? 'month' : 'day'
}

export function formatPartialDate(value: string | null | undefined): string | null {
  if (!value) return null
  const [year, month, day] = value.split('-')
  if (!month) return year
  const monthName = MONTHS[Number(month) - 1] ?? month
  if (!day) return `${monthName} ${year}`
  return `${day}/${month}/${year}`
}
