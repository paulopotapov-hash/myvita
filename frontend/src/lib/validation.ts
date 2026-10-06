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

export const invitationAcceptSchema = z.object({
  password: passwordSchema,
  confirm_password: z.string(),
}).refine((value) => value.password === value.confirm_password, {
  path: ['confirm_password'],
  message: 'As palavras-passe não coincidem.',
})

export const passwordChangeSchema = z.object({
  current_password: z.string().min(1, 'Introduz a palavra-passe atual.'),
  new_password: passwordSchema,
  confirm_password: z.string(),
}).refine((value) => value.new_password === value.confirm_password, {
  path: ['confirm_password'],
  message: 'As palavras-passe não coincidem.',
})

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
  staff_role: z.enum(['doctor', 'nurse', 'admin']),
  specialty: z.string().max(255).optional().or(z.literal('')),
})
export type StaffCreateFormValues = z.infer<typeof staffCreateSchema>

const durationMinutes = z.coerce
  .number('A duração deve ser um número de minutos.')
  .int('A duração deve ser um número inteiro de minutos.')
  .min(5, 'A duração mínima é de 5 minutos.')
  .max(480, 'A duração máxima é de 480 minutos.')

const reasonField = z.string().trim().max(500, 'O motivo pode ter no máximo 500 caracteres.')

export const appointmentCreateSchema = z.object({
  patient_id: z.string().min(1, 'Escolhe um paciente.'),
  staff_id: z.string().min(1, 'Escolhe um profissional.'),
  scheduled_at: z.string().min(1, 'Escolhe data e hora.'),
  duration_minutes: durationMinutes.default(30),
  reason: reasonField.optional().or(z.literal('')),
})
export type AppointmentCreateFormValues = z.infer<typeof appointmentCreateSchema>

export const appointmentUpdateSchema = z.object({
  duration_minutes: durationMinutes,
  reason: reasonField,
})

export const consentCreateSchema = z.object({
  consent_type: z.enum(['treatment', 'data_processing', 'communications', 'research']),
  purpose: z
    .string()
    .trim()
    .min(1, 'Indica a finalidade do consentimento.')
    .max(500, 'A finalidade pode ter no máximo 500 caracteres.'),
})

export const medicalRecordSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Indica o título do registo.')
    .max(200, 'O título pode ter no máximo 200 caracteres.'),
  content: z
    .string()
    .trim()
    .min(1, 'Indica o conteúdo clínico.')
    .max(20_000, 'O conteúdo pode ter no máximo 20 000 caracteres.'),
})

const optionalText = (max: number, message: string) => z.string().trim().max(max, message)

export const medicationFormSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, 'Indica o nome do medicamento.')
      .max(200, 'O nome pode ter no máximo 200 caracteres.'),
    dosage: z
      .string()
      .trim()
      .min(1, 'Indica a dosagem.')
      .max(200, 'A dosagem pode ter no máximo 200 caracteres.'),
    route: optionalText(100, 'A via de administração pode ter no máximo 100 caracteres.'),
    frequency: optionalText(100, 'A frequência pode ter no máximo 100 caracteres.'),
    instructions: optionalText(2000, 'As instruções podem ter no máximo 2000 caracteres.'),
    start_date: z.string().min(1, 'Indica a data de início.'),
    end_date: z.string(),
  })
  .refine((value) => !value.end_date || value.end_date >= value.start_date, {
    path: ['end_date'],
    message: 'A data de fim não pode ser anterior à data de início.',
  })
export type MedicationFormValues = z.infer<typeof medicationFormSchema>

export const patientUpdateSchema = z.object({
  phone: optionalText(30, 'O telefone pode ter no máximo 30 caracteres.'),
  national_health_number: optionalText(30, 'O número de utente pode ter no máximo 30 caracteres.'),
})

/** Authenticator-app code shown during MFA enrolment. */
export const mfaCodeSchema = z
  .string()
  .trim()
  .regex(/^\d{6}$/, 'Introduz o código de 6 dígitos mostrado na aplicação.')

/** Login second step: a 6-digit code or a (longer) recovery code. */
export const mfaVerificationCodeSchema = z
  .string()
  .trim()
  .min(6, 'Introduz o código de 6 dígitos ou um código de recuperação.')
