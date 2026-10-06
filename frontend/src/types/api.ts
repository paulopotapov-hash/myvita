/**
 * Types mirroring the backend's actual Pydantic schemas exactly
 * (backend/app/modules — each module's schemas.py). Only fields the backend really
 * returns — nothing invented ahead of the API contract.
 */

export type UserRole = 'patient' | 'staff' | 'clinic_admin'
export type StaffRole = 'doctor' | 'nurse' | 'physiotherapist' | 'admin'
export type AppointmentStatus = 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show'
export type ConsentType = 'treatment' | 'data_processing' | 'communications' | 'research'
export type ConsentStatus = 'granted' | 'revoked'
export type MedicationStatus = 'active' | 'discontinued' | 'completed'
export type DocumentKind = 'note' | 'file'
export type ConversationStatus = 'open' | 'waiting_for_patient' | 'waiting_for_team' | 'closed'
export type MessageSenderRole = 'patient' | 'doctor' | 'nurse'

export interface ClinicalMessagePublic {
  id: string
  sender_name: string
  sender_role: MessageSenderRole
  body: string
  created_at: string
}

export interface ConversationListItem {
  id: string
  patient_id: string
  patient_name: string
  subject: string
  status: ConversationStatus
  needs_doctor_review: boolean
  updated_at: string
  closed_at: string | null
  last_message: ClinicalMessagePublic
  unread: boolean
}

export interface ConversationDetail extends ConversationListItem {
  messages: ClinicalMessagePublic[]
}

export interface ClinicalDocumentPublic {
  id: string
  clinic_id: string
  patient_id: string
  kind: DocumentKind
  title: string
  current_version: number
  created_at: string
  updated_at: string
  current_content: string | null
  current_author: string | null
}

export interface ClinicalDocumentVersionPublic {
  id: string
  document_id: string
  author_name: string
  version: number
  content: string | null
  original_filename: string | null
  media_type: string | null
  file_size: number | null
  created_at: string
  is_current: boolean
}

/** What the account must do before anything else works
 * (backend/app/core/security.py pending_account_action). While set, every
 * endpoint except /auth/me, logout, change-password and MFA enrolment
 * answers 403 with the X-Account-Action-Required header. */
export type PendingAccountAction = 'password_change' | 'mfa_verification' | 'mfa_setup'

export interface UserPublic {
  id: string
  email: string
  full_name: string
  role: UserRole
  clinic_id: string | null
  staff_role: StaffRole | null
  patient_id: string | null
  // Always sent by the backend; optional here only so older fixtures that
  // predate account lifecycle still type-check. Absent means "nothing pending".
  must_change_password?: boolean
  mfa_enabled?: boolean
  mfa_required?: boolean
  pending_action?: PendingAccountAction | null
}

/** POST /auth/login answers 202 with this when a second factor is needed:
 * no session exists yet, only a short-lived challenge cookie. */
export interface MfaChallengeResponse {
  mfa_required: true
}

export function isMfaChallenge(value: UserPublic | MfaChallengeResponse): value is MfaChallengeResponse {
  return 'mfa_required' in value && value.mfa_required === true && !('id' in value)
}

export interface MfaSetupResponse {
  secret: string
  otpauth_uri: string
}

export interface MfaRecoveryCodesResponse {
  recovery_codes: string[]
}

export interface AccountSummary {
  id: string
  full_name: string
  role: UserRole
  staff_role: StaffRole | null
  /** Null for patients: administrative roles never see patient contact data. */
  email: string | null
  is_active: boolean
  mfa_enabled: boolean
  must_change_password: boolean
}

export interface PasswordResetIssued {
  user_id: string
  token: string
  expires_at: string
}

export interface ClinicPublic {
  id: string
  name: string
  nif: string | null
  address: string | null
  phone: string | null
}

/** Minimal, non-sensitive shape used by the public clinic picker. */
export interface ClinicSummary {
  id: string
  name: string
}

export interface PatientPublic {
  id: string
  clinic_id: string
  full_name: string
  birth_date: string | null // ISO date (YYYY-MM-DD), as sent by the backend
  phone: string | null
  national_health_number: string | null
  is_active: boolean
}

export interface PatientSummary {
  id: string
  clinic_id: string
  full_name: string
  is_active: boolean
}

export interface StaffPublic {
  id: string
  clinic_id: string
  full_name: string
  staff_role: StaffRole
  specialty: string | null
  is_active: boolean
}

export interface AppointmentPublic {
  id: string
  clinic_id: string
  patient_id: string
  staff_id: string
  scheduled_at: string // ISO datetime
  duration_minutes: number
  status: AppointmentStatus
  reason: string | null
}

export interface ConsentPublic {
  id: string
  clinic_id: string
  patient_id: string
  consent_type: ConsentType
  purpose: string
  status: ConsentStatus
  granted_at: string
  revoked_at: string | null
  recorded_by_user_id: string | null
  created_at: string
  updated_at: string
}

export interface MedicalRecordPublic {
  id: string
  clinic_id: string
  patient_id: string
  author_staff_id: string
  title: string
  content: string
  version: number
  created_at: string
  updated_at: string
}

export interface MedicalRecordRevisionPublic {
  id: string
  record_id: string
  editor_staff_id: string
  version: number
  title: string
  content: string
  created_at: string
}

export interface MedicationPublic {
  id: string
  clinic_id: string
  patient_id: string
  prescribed_by_staff_id: string
  name: string
  dosage: string
  route: string | null
  frequency: string | null
  instructions: string | null
  status: MedicationStatus
  start_date: string
  end_date: string | null
  created_at: string
  updated_at: string
}

export interface NotificationPublic {
  id: string
  title: string
  message: string
  is_read: boolean
  read_at: string | null
  created_at: string
  target_type?: string | null
  target_id?: string | null
  conversation_target_id?: string | null
}

// --- Request payloads (mirrors backend *Request schemas) --------------------

export interface LoginRequest {
  email: string
  password: string
}

export interface PublicConfig {
  clinic_onboarding_enabled: boolean
  patient_registration_enabled: boolean
}

export interface InvitationPreview {
  clinic_name: string
  email: string
  full_name: string
  role: Exclude<UserRole, 'clinic_admin'>
  staff_role: StaffRole | null
  expires_at: string
}

export interface InvitationAcceptRequest {
  token: string
  password: string
}

export interface StaffInvitationRequest {
  full_name: string
  email: string
  staff_role: StaffRole
  specialty?: string
}

export interface InvitationCreated extends StaffInvitationRequest {
  id: string
  clinic_id: string
  role: Exclude<UserRole, 'clinic_admin'>
  status: 'pending' | 'accepted' | 'revoked'
  token: string
  expires_at: string
  created_at: string
}

export interface PasswordChangeRequest {
  current_password: string
  new_password: string
}

export interface ClinicOnboardingRequest {
  clinic_name: string
  nif?: string
  address?: string
  phone?: string
  admin_full_name: string
  admin_email: string
  admin_password: string
}

export interface PatientRegisterRequest {
  clinic_id: string
  full_name: string
  email: string
  password: string
  birth_date?: string
  phone?: string
}

export interface AppointmentCreateRequest {
  patient_id: string
  staff_id: string
  scheduled_at: string
  duration_minutes?: number
  reason?: string
}

export interface ConsentCreateRequest {
  consent_type: ConsentType
  purpose: string
}

export interface PatientUpdateRequest {
  birth_date?: string | null
  phone?: string | null
  national_health_number?: string | null
}

export interface AppointmentUpdateRequest {
  patient_id?: string
  staff_id?: string
  scheduled_at?: string
  duration_minutes?: number
  reason?: string | null
  status?: Exclude<AppointmentStatus, 'cancelled'>
}

export interface MedicalRecordWriteRequest { title: string; content: string }
export interface MedicationCreateRequest {
  name: string
  dosage: string
  route?: string
  frequency?: string
  instructions?: string
  start_date: string
  end_date?: string
}
/** Only the fields the backend marks nullable can be cleared with `null`. */
export interface MedicationUpdateRequest {
  name?: string
  dosage?: string
  route?: string | null
  frequency?: string | null
  instructions?: string | null
  status?: MedicationStatus
  start_date?: string
  end_date?: string | null
}
export interface MedicationDeactivateRequest {
  end_date?: string
}
