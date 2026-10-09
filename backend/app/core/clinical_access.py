"""Central patient access and clinical-action policy.

Patient association and permission to perform an action are checked separately.
Role permissions mirror the current pilot access matrix; new roles receive no
clinical permissions until the product explicitly assigns them.
"""

import enum
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ClinicalCareAssignment, Patient, Staff, StaffRole, User, UserRole


class ClinicalAction(str, enum.Enum):
    VIEW_PATIENT = "patient.view"
    EDIT_PATIENT = "patient.edit"
    VIEW_MEDICAL_RECORDS = "medical_records.view"
    EDIT_MEDICAL_RECORDS = "medical_records.edit"
    VIEW_MEDICATIONS = "medications.view"
    EDIT_MEDICATIONS = "medications.edit"
    VIEW_CONSENTS = "consents.view"
    VIEW_APPOINTMENTS = "appointments.view"
    EDIT_APPOINTMENTS = "appointments.edit"
    VIEW_APPOINTMENT_REASON = "appointments.reason.view"
    INVITE_PATIENT = "patient.invite"
    VIEW_DOCUMENTS = "documents.view"
    EDIT_DOCUMENTS = "documents.edit"
    VIEW_CONVERSATIONS = "conversations.view"
    CREATE_CONVERSATIONS = "conversations.create"
    REPLY_CONVERSATIONS = "conversations.reply"
    TRIAGE_CONVERSATIONS = "conversations.triage"
    ESCALATE_CONVERSATIONS = "conversations.escalate"
    MANAGE_CONVERSATIONS = "conversations.manage"


# Explicit policy, not a role hierarchy. Doctor and nurse permissions reflect
# the existing docs/pilot-access-matrix.md. Other roles deny until configured.
_CURRENT_CLINICIAN_ACTIONS = frozenset(
    {
        ClinicalAction.VIEW_PATIENT,
        ClinicalAction.EDIT_PATIENT,
        ClinicalAction.VIEW_MEDICAL_RECORDS,
        ClinicalAction.EDIT_MEDICAL_RECORDS,
        ClinicalAction.VIEW_MEDICATIONS,
        ClinicalAction.EDIT_MEDICATIONS,
        ClinicalAction.VIEW_CONSENTS,
        ClinicalAction.VIEW_APPOINTMENTS,
        ClinicalAction.EDIT_APPOINTMENTS,
        ClinicalAction.VIEW_APPOINTMENT_REASON,
        ClinicalAction.INVITE_PATIENT,
        ClinicalAction.VIEW_DOCUMENTS,
        ClinicalAction.EDIT_DOCUMENTS,
        ClinicalAction.VIEW_CONVERSATIONS,
        ClinicalAction.CREATE_CONVERSATIONS,
        ClinicalAction.REPLY_CONVERSATIONS,
    }
)

ROLE_ACTIONS: dict[StaffRole, frozenset[ClinicalAction]] = {
    StaffRole.DOCTOR: _CURRENT_CLINICIAN_ACTIONS | {ClinicalAction.MANAGE_CONVERSATIONS},
    StaffRole.NURSE: _CURRENT_CLINICIAN_ACTIONS
    | {ClinicalAction.TRIAGE_CONVERSATIONS, ClinicalAction.ESCALATE_CONVERSATIONS},
    StaffRole.PHYSIOTHERAPIST: frozenset(),
    # Existing pilot matrix permits administrative staff to handle appointment
    # logistics. This does not grant access to clinical notes or demographics.
    StaffRole.ADMIN: frozenset({ClinicalAction.VIEW_APPOINTMENTS, ClinicalAction.EDIT_APPOINTMENTS}),
}

# Exposed for message-recipient filtering.  Keep it aligned with roles that
# are allowed any clinical action above.
CLINICAL_STAFF_ROLES = frozenset({StaffRole.DOCTOR, StaffRole.NURSE})

PATIENT_OWN_ACTIONS = frozenset(
    {
        ClinicalAction.VIEW_PATIENT,
        ClinicalAction.VIEW_MEDICAL_RECORDS,
        ClinicalAction.VIEW_MEDICATIONS,
        ClinicalAction.VIEW_CONSENTS,
        ClinicalAction.VIEW_DOCUMENTS,
        ClinicalAction.VIEW_CONVERSATIONS,
        ClinicalAction.REPLY_CONVERSATIONS,
        ClinicalAction.VIEW_APPOINTMENTS,
        ClinicalAction.VIEW_APPOINTMENT_REASON,
    }
)


def staff_profile(db: Session, user: User) -> Staff | None:
    if user.role != UserRole.STAFF or user.clinic_id is None:
        return None
    return db.query(Staff).filter(Staff.user_id == user.id, Staff.clinic_id == user.clinic_id).first()


def has_role_action(staff_role: StaffRole, action: ClinicalAction) -> bool:
    return action in ROLE_ACTIONS.get(staff_role, frozenset())


def clinical_access(
    db: Session,
    patient_id: uuid.UUID,
    user: User,
    action: ClinicalAction = ClinicalAction.VIEW_PATIENT,
) -> Patient:
    """Return the patient only when tenant, identity, assignment and action allow it."""
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")

    if user.role == UserRole.PATIENT:
        if patient.user_id != user.id or action not in PATIENT_OWN_ACTIONS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
        return patient

    staff = staff_profile(db, user)
    if staff is None or not has_role_action(staff.staff_role, action):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")

    if staff.staff_role == StaffRole.ADMIN and action in {
        ClinicalAction.VIEW_APPOINTMENTS,
        ClinicalAction.EDIT_APPOINTMENTS,
    }:
        return patient

    assigned = (
        db.query(ClinicalCareAssignment.id)
        .filter(
            ClinicalCareAssignment.clinic_id == user.clinic_id,
            ClinicalCareAssignment.patient_id == patient.id,
            ClinicalCareAssignment.staff_id == staff.id,
            ClinicalCareAssignment.active.is_(True),
        )
        .first()
    )
    if assigned is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso clínico a este paciente."
        )
    return patient


def clinical_staff(
    db: Session,
    user: User,
    patient_id: uuid.UUID | None = None,
    action: ClinicalAction | None = None,
) -> Staff:
    """Return a professional for a non-patient action or enforce scoped patient access."""
    staff = staff_profile(db, user)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    if patient_id is None:
        if action is None or not has_role_action(staff.staff_role, action):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    elif action is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    else:
        clinical_access(db, patient_id, user, action)
    return staff


def accessible_patient(db: Session, patient_id: uuid.UUID, user: User, *, write: bool = False) -> Patient:
    """Compatibility helper for the documents API, backed by the central policy."""
    return clinical_access(
        db,
        patient_id,
        user,
        ClinicalAction.EDIT_DOCUMENTS if write else ClinicalAction.VIEW_DOCUMENTS,
    )


def is_clinical_staff(db: Session, user: User, patient_id: uuid.UUID, action: ClinicalAction) -> bool:
    try:
        clinical_staff(db, user, patient_id, action)
    except HTTPException:
        return False
    return True
