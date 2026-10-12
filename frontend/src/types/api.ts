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

/** E-mail delivery of a one-time link: "sent" = accepted by the relay; otherwise hand the link over. */
export type EmailDelivery = 'sent' | 'failed' | 'disabled'

export interface PasswordResetIssued {
  user_id: string
  token: string
  expires_at: string
  delivery: EmailDelivery
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
  address: PatientAddress
  /** Masked by the server: only the last three digits (full values need the audited reveal). */
  identifiers: PatientIdentifiers
  is_active: boolean
}

export interface PatientAddress {
  street: string | null
  postal_code: string | null
  locality: string | null
}

/** NIF, NISS and Nº de utente do SNS. Masked ("••••••789") unless returned by the reveal endpoint. */
export interface PatientIdentifiers {
  nif: string | null
  niss: string | null
  national_health_number: string | null
}

/** Name and masked identifiers; also served to administrative staff and the clinic administrator. */
export interface PatientIdentification {
  id: string
  full_name: string
  identifiers: PatientIdentifiers
  can_edit: boolean
}

export type PatientIdentifiersUpdateRequest = Partial<{ [K in keyof PatientIdentifiers]: string | null }>

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

/** Staff and clinic-admin view (backend AppointmentPublic). */
export interface AppointmentPublic {
  view: 'staff'
  id: string
  clinic_id: string
  patient_id: string
  staff_id: string
  scheduled_at: string // ISO datetime
  duration_minutes: number
  status: AppointmentStatus
  reason: string | null
}

/** Patient view: the professional's display name, no internal identifiers. */
export interface AppointmentPatientView {
  view: 'patient'
  id: string
  staff_name: string
  scheduled_at: string // ISO datetime
  ends_at: string
  duration_minutes: number
  status: AppointmentStatus
  reason: string | null
  /** "Consulta" for appointments made before appointment types existed. */
  appointment_type: string
  specialty: string | null
  /** The clinic's address. */
  location: string | null
  /** Whether the patient may still cancel or reschedule in the app (server rule). */
  can_change: boolean
  /** Until when (the clinic's deadline); null once it is no longer active. */
  change_until: string | null
  /** How it is rescheduled: free slots ("direct") or a request to the clinic; null without a type. */
  booking_mode: 'direct' | 'request' | null
  /** The patient confirmed they will come (step 7). */
  patient_confirmed_at: string | null
  can_confirm: boolean
}

export type AppointmentView = AppointmentPublic | AppointmentPatientView

export type AppointmentRequestStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled' | 'proposed' | 'declined'
export type RequestPeriod = 'morning' | 'afternoon'

/**
 * Patient-submitted request; patient/clinic come from the session. Either one preferred
 * time, or a window (from/to, weekdays 0 = Monday, morning/afternoon). `reschedule_of_id`
 * asks to move one of the patient's appointments (its type is kept).
 */
export interface AppointmentRequestCreate {
  preferred_start?: string // ISO datetime with timezone
  preferred_from?: string // YYYY-MM-DD
  preferred_to?: string
  preferred_weekdays?: number[]
  preferred_period?: RequestPeriod
  appointment_type_id?: string
  staff_id?: string
  reschedule_of_id?: string
  reason?: string
}

/** Staff choose (accept) or propose the professional and slot; duration defaults to the type's. */
export interface AppointmentRequestAccept {
  staff_id: string
  scheduled_at: string // ISO datetime with timezone
  duration_minutes?: number
}

export interface AppointmentRequestPublic {
  id: string
  clinic_id: string
  patient_id: string
  patient_name: string
  preferred_start: string | null
  preferred_from: string | null
  preferred_to: string | null
  preferred_weekdays: number[] | null
  preferred_period: RequestPeriod | null
  appointment_type: string | null
  specialty: string | null
  /** Professional ids are given to staff only (null for the patient); names to everyone. */
  staff_id: string | null
  staff_name: string | null
  reschedule_of_id: string | null
  reschedule_of_start: string | null
  proposed_staff_id: string | null
  proposed_staff_name: string | null
  proposed_start: string | null
  proposed_duration_minutes: number | null
  /** null when the caller may not read clinical content. */
  reason: string | null
  status: AppointmentRequestStatus
  appointment_id: string | null
  decided_at: string | null
  created_at: string
}

/** Staff view of a consent. Patients receive ConsentPatientView (no internal identifiers). */
export interface ConsentPublic {
  view: 'staff'
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

export interface ConsentPatientView {
  view: 'patient'
  id: string
  consent_type: ConsentType
  purpose: string
  policy_version: string | null
  policy_text: string | null
  status: ConsentStatus
  granted_at: string
  revoked_at: string | null
  created_at: string
  updated_at: string
}

export type ConsentView = ConsentPublic | ConsentPatientView

/**
 * P2.5 visibility. 'internal': care team only (default). 'shared': a professional
 * explicitly shared it with the patient. 'legacy_shared': pre-dates the visibility
 * model and stays readable by the patient, but nobody made a sharing decision.
 */
export type MedicalRecordVisibility = 'internal' | 'shared' | 'legacy_shared'

/** Professional view of a record (backend MedicalRecordPublic, `view: 'staff'`). */
export interface MedicalRecordPublic {
  view: 'staff'
  id: string
  clinic_id: string
  patient_id: string
  author_staff_id: string
  /** Shown in the UI instead of the internal staff id. */
  author_name: string
  title: string
  content: string
  visibility: MedicalRecordVisibility
  /** Last explicit share/unshare decision; null for new and legacy records. */
  visibility_changed_at: string | null
  visibility_changed_by_name: string | null
  version: number
  created_at: string
  updated_at: string
}

/** Patient view: only shared records, without staff ids, versions or sharing metadata. */
export interface MedicalRecordPatientView {
  view: 'patient'
  id: string
  author_name: string
  title: string
  content: string
  created_at: string
  updated_at: string
}

export type MedicalRecordView = MedicalRecordPublic | MedicalRecordPatientView

export interface MedicalRecordRevisionPublic {
  id: string
  record_id: string
  editor_staff_id: string
  /** Shown in the UI instead of the internal staff id. */
  editor_name: string
  version: number
  title: string
  content: string
  visibility: MedicalRecordVisibility
  created_at: string
}

// --- Clinical results (backend/app/modules/clinical_results/schemas.py) ---

export type ClinicalResultCategory = 'laboratory' | 'imaging' | 'pathology' | 'other'
export type ClinicalResultStatus = 'draft' | 'released'

interface ClinicalResultCommon {
  id: string
  category: ClinicalResultCategory
  title: string
  value: string | null
  unit: string | null
  reference_range: string | null
  summary: string | null
  /** Clinical date of the result (YYYY-MM-DD). */
  result_date: string
  /** Optional link to an existing document of the same patient. */
  document_id: string | null
  author_name: string
}

/** Professional view, including the draft → released workflow state and the correction chain. */
export interface ClinicalResultStaffView extends ClinicalResultCommon {
  view: 'staff'
  patient_id: string
  status: ClinicalResultStatus
  released_at: string | null
  released_by_name: string | null
  /** Set on a correction: the released result it corrects, and why. */
  corrects_result_id: string | null
  correction_reason: string | null
  /** The correction of this result, draft or released. */
  corrected_by_result_id: string | null
  /** A released correction replaces this result for the patient. */
  superseded: boolean
  created_at: string
  updated_at: string
}

/** Patient view: released results only, no workflow fields and no internal correction reason. */
export interface ClinicalResultPatientView extends ClinicalResultCommon {
  view: 'patient'
  released_at: string
  corrects_result_id: string | null
  /** The released correction of this result, if any. */
  superseded_by_result_id: string | null
}

export type ClinicalResultPublic = ClinicalResultStaffView | ClinicalResultPatientView

export interface ClinicalResultCreateRequest {
  category: ClinicalResultCategory
  title: string
  value?: string
  unit?: string
  reference_range?: string
  summary?: string
  result_date: string
  document_id?: string
  /** Make the result available to the patient immediately (otherwise a draft). */
  release?: boolean
}

/** A correction of a released result: the complete corrected result plus a reason. */
export interface ClinicalResultCorrectionRequest extends ClinicalResultCreateRequest {
  correction_reason: string
}

/** Drafts only; nullable fields can be cleared with `null`. */
export interface ClinicalResultUpdateRequest {
  category?: ClinicalResultCategory
  title?: string
  value?: string | null
  unit?: string | null
  reference_range?: string | null
  summary?: string | null
  result_date?: string
  document_id?: string | null
  /** Draft corrections only. */
  correction_reason?: string
}

/** Fields shared by every medication view. */
export interface MedicationFields {
  id: string
  name: string
  /** Optional only in a patient's declaration (the professional may complete it on confirmation). */
  dosage: string | null
  route: string | null
  frequency: string | null
  instructions: string | null
  status: MedicationStatus
  /** "2020", "2020-03" or "2020-03-12"; always complete for a professional's prescription, optional in a declaration. */
  start_date: string | null
  end_date: string | null
  origin: HistoryOrigin
  confirmed: boolean
  created_at: string
  updated_at: string
}

/** Professional view (care team). */
export interface MedicationPublic extends MedicationFields {
  view: 'staff'
  clinic_id: string
  patient_id: string
  prescribed_by_staff_id: string | null
  confirmed_at: string | null
  confirmed_by_staff_id: string | null
  /** Hidden from the patient by the care team, with a reason. */
  hidden: boolean
  hidden_at: string | null
  hidden_reason: string | null
}

/** Patient view: no internal clinic or staff identifiers, nothing about hiding. */
export interface MedicationPatientView extends MedicationFields {
  view: 'patient'
  /** The patient's own declaration, not yet confirmed. */
  can_edit: boolean
}

export type MedicationView = MedicationPublic | MedicationPatientView

export interface NotificationPublic {
  id: string
  title: string
  message: string
  is_read: boolean
  read_at: string | null
  created_at: string
  /** Deep-link target: 'document' uses `target_id`, 'conversation' uses `conversation_target_id`,
   * 'result' uses `result_target_id`, 'medical_record' uses `record_target_id`, 'appointment'
   * (reminders) uses `appointment_target_id`. The target page re-checks access on open. */
  target_type: 'document' | 'conversation' | 'result' | 'medical_record' | 'appointment' | 'patient' | null
  target_id: string | null
  conversation_target_id: string | null
  result_target_id?: string | null
  record_target_id?: string | null
  appointment_target_id?: string | null
  /** 'patient' (profile photo): the patient's file for staff, the profile for the patient. */
  patient_target_id?: string | null
}

/** Uploader is exposed by display name only, never by internal user id. */
export interface DocumentPublic {
  id: string
  patient_id: string
  title: string
  uploaded_by_name: string
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
  delivery: EmailDelivery
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

/** Contact data. The patient may change phone and address only (identifiers have their own endpoint). */
export interface PatientUpdateRequest {
  birth_date?: string | null
  phone?: string | null
  address_street?: string | null
  address_postal_code?: string | null
  address_locality?: string | null
}

export interface AppointmentUpdateRequest {
  patient_id?: string
  staff_id?: string
  scheduled_at?: string
  duration_minutes?: number
  reason?: string | null
  status?: Exclude<AppointmentStatus, 'cancelled'>
}

/** `share_with_patient` is the author's explicit decision to share the new record. */
export interface MedicalRecordCreateRequest { title: string; content: string; share_with_patient?: boolean }
/** Content only: visibility changes go through share/unshare. */
export interface MedicalRecordUpdateRequest { title: string; content: string; expected_version: number }
export interface MedicationCreateRequest {
  name: string
  /** Required for a professional's prescription; optional in a patient's declaration. */
  dosage?: string
  route?: string
  frequency?: string
  instructions?: string
  /** Required and complete for professionals; optional and possibly partial in a declaration. */
  start_date?: string
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
  /** `null` only in the patient's own declaration. */
  start_date?: string | null
  end_date?: string | null
}
export interface MedicationDeactivateRequest {
  end_date?: string
}

// --- Clinical history (backend/app/modules/clinical_history/schemas.py) ---

export type HistoryCategory = 'condition' | 'procedure' | 'allergy' | 'immunization' | 'note'
/** Who created the entry; with `confirmed` it gives "Confirmado pelo profissional" / "Declarado pelo paciente". */
export type HistoryOrigin = 'professional' | 'patient_declared'
export type ConditionStatus = 'active' | 'resolved'
export type AllergySeverity = 'mild' | 'moderate' | 'severe' | 'unknown'

/** Content fields. Dates are partial: "2010", "2010-03" or "2010-03-12". */
export interface ClinicalHistoryFields {
  name: string | null
  condition_status: ConditionStatus | null
  onset: string | null
  resolved: string | null
  occurred: string | null
  location: string | null
  reaction: string | null
  severity: AllergySeverity | null
  note_text: string | null
}

interface ClinicalHistoryCommon extends ClinicalHistoryFields {
  id: string
  category: HistoryCategory
  origin: HistoryOrigin
  confirmed: boolean
  confirmed_at: string | null
  confirmed_by_name: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface ClinicalHistoryStaffView extends ClinicalHistoryCommon {
  view: 'staff'
  created_by_name: string
  hidden: boolean
  hidden_at: string | null
  hidden_reason: string | null
  hidden_by_name: string | null
}

/** Patient view: hidden entries are never sent, and nothing about hiding is. */
export interface ClinicalHistoryPatientView extends ClinicalHistoryCommon {
  view: 'patient'
  /** The patient's own declaration, not yet confirmed. */
  can_edit: boolean
}

export type ClinicalHistoryEntry = ClinicalHistoryStaffView | ClinicalHistoryPatientView

export type ClinicalHistoryCreateRequest = { category: HistoryCategory } & Partial<ClinicalHistoryFields>
export type ClinicalHistoryUpdateRequest = Partial<ClinicalHistoryFields> & { expected_version: number }

// --- Messages (backend/app/modules/messages/schemas.py) ---

/** Mirrors backend MESSAGE_MAX_LENGTH; the backend still validates. */
export const MESSAGE_MAX_LENGTH = 5000

/** Care-team workflow state. Messages move it between the waiting states; only a doctor closes. */
export type ConversationStatus = 'open' | 'waiting_for_patient' | 'waiting_for_team' | 'closed'

/** Staff only: triage metadata never reaches the patient (`team` is null for patients). */
export interface ConversationTeamState {
  needs_doctor_review: boolean
  escalated_at: string | null
  escalated_by_name: string | null
  closed_by_name: string | null
}

export interface ConversationPublic {
  id: string
  /** Staff only; null for patients, who are shown names instead. */
  clinic_id: string | null
  patient_id: string | null
  staff_id: string | null
  patient_name: string
  /** The professional who opened the thread; the patient's active care team shares it. */
  staff_name: string
  status: ConversationStatus
  closed_at: string | null
  /** Patient: team messages not read yet. Staff: patient messages nobody on the team has opened. */
  unread_count: number
  /** False when closed, or when nobody on the care team could read a patient reply. */
  can_reply: boolean
  team: ConversationTeamState | null
  created_at: string
  /** Latest activity (last message, or creation). */
  updated_at: string
}

export type MessageSenderRole = 'patient' | 'doctor' | 'nurse' | 'staff'

export interface MessagePublic {
  id: string
  conversation_id: string
  sender_name: string
  sender_role: MessageSenderRole
  /** Written by the current user (no internal user ids are exposed). */
  is_mine: boolean
  body: string
  read_at: string | null
  created_at: string
}

export interface ConversationDetail extends ConversationPublic {
  /** One page, newest first. */
  messages: MessagePublic[]
}

/** Clinical staff send patient_id; patients send staff_id. */
/** Only clinical staff start conversations, with a patient on their care team. */
export interface ConversationCreateRequest {
  patient_id: string
}
