import type { UserPublic, UserRole } from '../types/api'

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  patient: 'Paciente',
  staff: 'Profissional de saúde',
  clinic_admin: 'Administrador da clínica',
}

/**
 * Doctor or nurse: the only roles the backend currently grants clinical
 * actions (backend/app/core/clinical_access.py). UX only — the backend still
 * enforces the per-patient care assignment on every request.
 */
export function isClinician(user: UserPublic | null | undefined): boolean {
  return user?.role === 'staff' && (user.staff_role === 'doctor' || user.staff_role === 'nurse')
}
