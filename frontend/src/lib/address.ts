import type { PatientAddress } from '../types/api'

/** "Rua Sintética, 1, 1000-001 Lisboa", or null when nothing is filled in. */
export function formatAddress(address: PatientAddress | undefined): string | null {
  if (!address) return null
  const place = [address.postal_code, address.locality].filter(Boolean).join(' ')
  const text = [address.street, place].filter(Boolean).join(', ')
  return text || null
}
