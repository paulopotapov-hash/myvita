/**
 * Portuguese identifiers, mirroring backend/app/core/pt_identifiers.py so forms can
 * explain mistakes before sending. The backend validates again and is the authority.
 */

/** Accept the usual spaced formats ("123 456 789"). */
export function digitsOnly(value: string): string {
  return value.replace(/\s+/g, '')
}

export function isValidNif(value: string): boolean {
  if (!/^\d{9}$/.test(value)) return false
  const total = [...value.slice(0, 8)].reduce((sum, digit, index) => sum + Number(digit) * (9 - index), 0)
  const remainder = total % 11
  const check = remainder < 2 ? 0 : 11 - remainder
  return check === Number(value[8])
}

const NISS_WEIGHTS = [29, 23, 19, 17, 13, 11, 7, 5, 3, 2]

export function isValidNiss(value: string): boolean {
  if (!/^[12]\d{10}$/.test(value)) return false
  const total = NISS_WEIGHTS.reduce((sum, weight, index) => sum + Number(value[index]) * weight, 0)
  return 9 - (total % 10) === Number(value[10])
}

export function isValidSnsNumber(value: string): boolean {
  return /^\d{9}$/.test(value)
}

export function isValidPostalCode(value: string): boolean {
  return /^\d{4}-\d{3}$/.test(value)
}
