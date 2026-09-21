import { z } from 'zod'

/** Flattens a ZodError into `{ field: message }` for direct use as form
 * field errors — merges naturally with ApiError.fieldErrors from the
 * backend (see lib/apiClient.ts), which uses the same shape. */
export function zodErrorsToRecord(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {}
  for (const issue of error.issues) {
    const field = String(issue.path[0] ?? '_root')
    if (!out[field]) out[field] = issue.message
  }
  return out
}


/**
 * Mirrors backend/app/core/validators.py + each module's Field(...)
 * constraints exactly. This is UX-only — the backend re-validates
 * everything and is the actual authority (see each module's schemas.py
 * under backend/app/modules).
 * Keeping the two in sync is a deliberate choice made when either side
 * changes, not an assumption that they'll drift together automatically.
 */

export const loginSchema = z.object({
  email: z.email('Introduz um email válido.'),
  password: z.string().min(1, 'Introduz a palavra-passe.'),
})
export type LoginFormValues = z.infer<typeof loginSchema>

// Same weak-password blocklist as backend/app/core/validators.py — the
// backend is what actually enforces this; this just avoids a round-trip
// for the most obvious cases.
const COMMON_WEAK_PASSWORDS = new Set([
  'password',
  'password1',
  'password123',
  '12345678',
  '123456789',
  'qwerty123',
  'letmein',
  'admin123',
  'abc12345',
])

const passwordSchema = z
  .string()
  .min(8, 'A palavra-passe precisa de pelo menos 8 caracteres.')
  .max(128, 'A palavra-passe é demasiado longa.')
  .refine((value) => !COMMON_WEAK_PASSWORDS.has(value.toLowerCase()), 'Palavra-passe demasiado fraca.')
  .refine((value) => new Set(value).size > 2, 'Palavra-passe demasiado fraca.')

export const clinicOnboardingSchema = z.object({
  clinic_name: z.string().min(2, 'Nome demasiado curto.').max(255),
  nif: z.string().max(20).optional().or(z.literal('')),
  address: z.string().max(500).optional().or(z.literal('')),
  phone: z.string().max(30).optional().or(z.literal('')),
  admin_full_name: z.string().min(2, 'Nome demasiado curto.').max(255),
  admin_email: z.email('Introduz um email válido.'),
  admin_password: passwordSchema,
})
export type ClinicOnboardingFormValues = z.infer<typeof clinicOnboardingSchema>

export const patientRegisterSchema = z.object({
  clinic_id: z.string().min(1, 'Escolhe uma clínica.'),
  full_name: z.string().min(2, 'Nome demasiado curto.').max(255),
  email: z.email('Introduz um email válido.'),
  password: passwordSchema,
  birth_date: z.string().optional().or(z.literal('')),
  phone: z.string().max(30).optional().or(z.literal('')),
})
export type PatientRegisterFormValues = z.infer<typeof patientRegisterSchema>

export const staffCreateSchema = z.object({
  full_name: z.string().min(2, 'Nome demasiado curto.').max(255),
  email: z.email('Introduz um email válido.'),
  password: passwordSchema,
  staff_role: z.enum(['doctor', 'nurse', 'admin']),
  specialty: z.string().max(255).optional().or(z.literal('')),
  license_number: z.string().max(50).optional().or(z.literal('')),
})
export type StaffCreateFormValues = z.infer<typeof staffCreateSchema>

export const appointmentCreateSchema = z.object({
  patient_id: z.string().min(1, 'Escolhe um paciente.'),
  staff_id: z.string().min(1, 'Escolhe um profissional.'),
  scheduled_at: z.string().min(1, 'Escolhe data e hora.'),
  duration_minutes: z.coerce.number().int().min(5).max(480).default(30),
  reason: z.string().max(500).optional().or(z.literal('')),
})
export type AppointmentCreateFormValues = z.infer<typeof appointmentCreateSchema>
