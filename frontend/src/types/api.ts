/**
 * Types mirroring the backend's actual Pydantic schemas exactly
 * (backend/app/modules — each module's schemas.py). Only fields the backend really
 * returns — nothing invented ahead of the API contract.
 */

export type UserRole = 'patient' | 'staff' | 'clinic_admin'
export type StaffRole = 'doctor' | 'nurse' | 'admin'
export type AppointmentStatus = 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show'
export type ConsentType = 'treatment' | 'data_processing' | 'communications' | 'research'
export type ConsentStatus = 'granted' | 'revoked'
export type MedicationStatus = 'active' | 'discontinued' | 'completed'

export interface UserPublic {
  id: string
  email: string
  full_name: string
  role: UserRole
  clinic_id: string | null
  staff_role: StaffRole | null
  patient_id: string | null
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

export type AppointmentRequestStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled'

/** Patient-submitted request; patient/clinic come from the session, the professional is chosen by staff. */
export interface AppointmentRequestCreate {
  preferred_start: string // ISO datetime with timezone
  reason?: string
}

export interface AppointmentRequestAccept {
  staff_id: string
  scheduled_at: string // ISO datetime with timezone
  duration_minutes: number
}

export interface AppointmentRequestPublic {
  id: string
  clinic_id: string
  patient_id: string
  patient_name: string
  preferred_start: string
  /** null when the caller may not read clinical content. */
  reason: string | null
  status: AppointmentRequestStatus
  appointment_id: string | null
  decided_at: string | null
  created_at: string
}

export interface ConsentPublic {
  id: string
  clinic_id: string
  patient_id: string
  consent_type: ConsentType
  purpose: string
  policy_version: string | null
  policy_text: string | null
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
}

export interface DocumentPublic {
  id: string
  patient_id: string
  uploaded_by_user_id: string
  original_filename: string
  content_type: string
  file_size: number
  created_at: string
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

export interface PatientInvitationRequest {
  full_name: string
  email: string
}

/** Invitation as listed for management: never carries the token. */
export interface InvitationPublic {
  id: string
  clinic_id: string
  email: string
  full_name: string
  role: Exclude<UserRole, 'clinic_admin'>
  staff_role: StaffRole | null
  status: 'pending' | 'accepted' | 'revoked'
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

export interface StaffCreateRequest {
  full_name: string
  email: string
  password: string
  staff_role: StaffRole
  specialty?: string
  license_number?: string
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
  policy_version?: string
  policy_text?: string
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

export interface MedicalRecordCreateRequest { title: string; content: string }
export interface MedicalRecordUpdateRequest extends MedicalRecordCreateRequest { expected_version: number }
export interface MedicationCreateRequest {
  name: string
  dosage: string
  instructions?: string
  start_date: string
  end_date?: string
}
export interface MedicationUpdateRequest {
  dosage?: string
  instructions?: string | null
  status?: MedicationStatus
  end_date?: string | null
}

// --- Messages (backend/app/modules/messages/schemas.py) ---

/** Mirrors backend MESSAGE_MAX_LENGTH; the backend still validates. */
export const MESSAGE_MAX_LENGTH = 5000

export interface ConversationPublic {
  id: string
  clinic_id: string
  patient_id: string
  staff_id: string
  patient_name: string
  staff_name: string
  /** Messages addressed to the current user that they haven't read. */
  unread_count: number
  created_at: string
  /** Latest activity (last message, or creation). */
  updated_at: string
}

export interface MessagePublic {
  id: string
  conversation_id: string
  sender_user_id: string
  body: string
  read_at: string | null
  created_at: string
}

export interface ConversationDetail extends ConversationPublic {
  /** One page, newest first. */
  messages: MessagePublic[]
}

/** Clinical staff send patient_id; patients send staff_id. */
export type ConversationCreateRequest = { patient_id: string } | { staff_id: string }
