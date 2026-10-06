import { useClinics } from './useClinicData'
import { useSession } from './useSession'

/** There's no "get my clinic" endpoint — only the public directory
 * (GET /api/v1/clinics, id+name only) and the onboarding endpoint. This
 * resolves the current user's own clinic name from that public list
 * rather than adding a new backend endpoint for a single display string. */
export function useOwnClinicName(): string | null {
  const { user } = useSession()
  const clinics = useClinics()
  if (!user?.clinic_id || !clinics.data) return null
  return clinics.data.find((c) => c.id === user.clinic_id)?.name ?? null
}
