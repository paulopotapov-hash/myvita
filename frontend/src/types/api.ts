/**
 * Types mirroring the backend's actual Pydantic schemas exactly
 * (backend/app/modules — each module's schemas.py). Only fields the backend really
 * returns — nothing invented ahead of the API contract.
 */

export type UserRole = 'patient' | 'staff' | 'clinic_admin'
export type StaffRole = 'doctor' | 'nurse' | 'admin'
export type AppointmentStatus = 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show'

export interface UserPublic {
  id: string
  email: string
  full_name: string
  role: UserRole
  clinic_id: string | null
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
