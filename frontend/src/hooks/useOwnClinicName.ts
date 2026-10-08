import { useClinic } from './useClinicData'
import { useSession } from './useSession'

/** Resolves the current user's own clinic name from GET /api/v1/clinics/{id}.
 * A signed-in user can always see their own clinic; the backend 404s anything
 * else, so this never depends on the (paginated, visibility-filtered) list. */
export function useOwnClinicName(): string | null {
  const { user } = useSession()
  const clinic = useClinic(user?.clinic_id)
  return clinic.data?.name ?? null
}
