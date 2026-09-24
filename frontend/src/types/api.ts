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

export interface StaffPublic {
  id: string
  clinic_id: string
  full_name: string
  staff_role: StaffRole
  specialty: string | null
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

// --- Request payloads (mirrors backend *Request schemas) --------------------

export interface LoginRequest {
  email: string
  password: string
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
