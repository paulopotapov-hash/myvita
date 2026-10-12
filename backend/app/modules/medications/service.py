"""Medication: prescriptions by the care team and, since commit 3, the patient's declarations.

- Doctors and nurses with an active care assignment prescribe (dose required), edit,
  finish, confirm declarations (and may complete the dose), hide an entry from the
  patient with a reason (D4), show it again and delete it with a reason.
- The patient reads their own medication that is not hidden, declares medication
  (dose optional, D6) and edits or deletes their own declarations until confirmed (D3).
- Deletion is soft: the runtime database role has no DELETE on medications (D8).
"""

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.core.partial_dates import PartialDateError, parse_partial_date
from app.models import DatePrecision, HistoryOrigin, Medication, MedicationStatus, Staff, User, UserRole
from app.modules.medications.schemas import (
    MedicationConfirmRequest,
    MedicationCreateRequest,
    MedicationDeactivateRequest,
    MedicationDeleteRequest,
    MedicationHideRequest,
    MedicationUpdateRequest,
)

NOT_FOUND = "Medicação não encontrada."
PATIENT_LOCKED = "Só podes alterar a medicação que declaraste e que ainda não foi confirmada."
PATIENT_FIELDS = frozenset({"name", "dosage", "route", "frequency", "instructions", "start_date", "end_date"})


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"type": "value_error", "loc": ["body", field], "msg": message}],
    )


def _start(raw: str | None, *, professional: bool) -> tuple[date | None, DatePrecision | None]:
    """Start date and its precision. Complete and required from professionals; optional
    and possibly partial ("2020", "2020-03") in a patient's declaration."""
    if raw is None:
        if professional:
            raise _field_error("start_date", "Indica a data de início.")
        return None, None
    try:
        parsed, precision = parse_partial_date(raw, allow_future=True)
    except PartialDateError as exc:
        raise _field_error("start_date", str(exc)) from exc
    if professional and precision != DatePrecision.DAY:
        raise _field_error("start_date", "Indica a data de início completa.")
    return parsed, precision


def _check_order(medication: Medication) -> None:
    if medication.end_date is not None and medication.start_date is not None and medication.end_date < medication.start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Data final inválida.")


def is_own_open_declaration(medication: Medication, user: User) -> bool:
    return (
        user.role == UserRole.PATIENT
        and medication.origin == HistoryOrigin.PATIENT_DECLARED
        and medication.declared_by_user_id == user.id
        and medication.confirmed_at is None
    )


def _visible(query: "Query[Medication]", user: User) -> "Query[Medication]":
    query = query.filter(Medication.deleted_at.is_(None))
    if user.role == UserRole.PATIENT:
        # Hidden by the care team (D4): it does not exist for the patient.
        query = query.filter(Medication.hidden_at.is_(None))
    return query


def list_medications(
    db: Session,
    patient_id: uuid.UUID,
    user: User,
    *,
    medication_status: MedicationStatus | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Medication], int]:
    clinical_access(db, patient_id, user, ClinicalAction.VIEW_MEDICATIONS)
    query = _visible(
        db.query(Medication).filter(Medication.patient_id == patient_id, Medication.clinic_id == user.clinic_id), user
    )
    if medication_status is not None:
        query = query.filter(Medication.status == medication_status)
    total = query.count()
    medications = (
        query.order_by(Medication.created_at.desc(), Medication.id.desc()).offset(offset).limit(limit).all()
    )
    return medications, total


def get_medication(db: Session, medication_id: uuid.UUID, user: User, *, lock: bool = False) -> Medication:
    query = _visible(
        db.query(Medication).filter(Medication.id == medication_id, Medication.clinic_id == user.clinic_id), user
    )
    medication = (query.with_for_update() if lock else query).first()
    if medication is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    clinical_access(db, medication.patient_id, user, ClinicalAction.VIEW_MEDICATIONS)
    return medication


def _professional(db: Session, medication: Medication, user: User) -> Staff:
    clinical_access(db, medication.patient_id, user, ClinicalAction.EDIT_MEDICATIONS)
    return clinical_staff(db, user, medication.patient_id, ClinicalAction.EDIT_MEDICATIONS)


def create_medication(
    db: Session, patient_id: uuid.UUID, payload: MedicationCreateRequest, user: User
) -> Medication:
    values = payload.model_dump()
    professional = user.role != UserRole.PATIENT
    values["start_date"], values["start_precision"] = _start(values.get("start_date"), professional=professional)
    if user.role == UserRole.PATIENT:
        patient = clinical_access(db, patient_id, user, ClinicalAction.DECLARE_CLINICAL_HISTORY)
        medication = Medication(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            origin=HistoryOrigin.PATIENT_DECLARED,
            declared_by_user_id=user.id,
            **values,
        )
    else:
        patient = clinical_access(db, patient_id, user, ClinicalAction.EDIT_MEDICATIONS)
        staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_MEDICATIONS)
        if values.get("dosage") is None:
            raise _field_error("dosage", "Indica a dosagem.")
        medication = Medication(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            origin=HistoryOrigin.PROFESSIONAL,
            prescribed_by_staff_id=staff.id,
            confirmed_by_staff_id=staff.id,
            confirmed_at=datetime.now(UTC),
            **values,
        )
    _check_order(medication)
    db.add(medication)
    db.commit()
    db.refresh(medication)
    return medication


def update_medication(
    db: Session, medication_id: uuid.UUID, payload: MedicationUpdateRequest, user: User
) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if user.role == UserRole.PATIENT:
        if not is_own_open_declaration(medication, user) or not set(changes) <= PATIENT_FIELDS:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PATIENT_LOCKED)
    else:
        _professional(db, medication, user)
    if medication.status != MedicationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Medicação já terminada.")
    if (
        changes.get("status") in {MedicationStatus.COMPLETED, MedicationStatus.DISCONTINUED}
        and changes.get("end_date") is None
    ):
        changes["end_date"] = date.today()
    if "start_date" in changes:
        changes["start_date"], changes["start_precision"] = _start(
            changes["start_date"], professional=user.role != UserRole.PATIENT
        )
    for field, value in changes.items():
        setattr(medication, field, value)
    _check_order(medication)
    db.commit()
    db.refresh(medication)
    return medication


def deactivate_medication(
    db: Session,
    medication_id: uuid.UUID,
    payload: MedicationDeactivateRequest | None,
    user: User,
) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    _professional(db, medication, user)
    if medication.status != MedicationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Medicação já terminada.")
    requested_end = payload.end_date if payload is not None else None
    start = medication.start_date or date.today()
    end_date = requested_end or max(date.today(), start)
    if end_date < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Data final inválida.")
    medication.status = MedicationStatus.DISCONTINUED
    medication.end_date = end_date
    db.commit()
    db.refresh(medication)
    return medication


def confirm_medication(
    db: Session, medication_id: uuid.UUID, payload: MedicationConfirmRequest, user: User
) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    staff = _professional(db, medication, user)
    if medication.confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta medicação já está confirmada.")
    if payload.dosage is not None:
        medication.dosage = payload.dosage
    if payload.start_date is not None:
        # Completing the patient's partial (or missing) start date with the full date.
        medication.start_date, medication.start_precision = payload.start_date, DatePrecision.DAY
        _check_order(medication)
    medication.confirmed_by_staff_id, medication.confirmed_at = staff.id, datetime.now(UTC)
    db.commit()
    db.refresh(medication)
    return medication


def hide_medication(db: Session, medication_id: uuid.UUID, payload: MedicationHideRequest, user: User) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    staff = _professional(db, medication, user)
    if medication.hidden_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta medicação já está oculta ao paciente.")
    medication.hidden_by_staff_id, medication.hidden_at, medication.hidden_reason = (
        staff.id,
        datetime.now(UTC),
        payload.reason,
    )
    db.commit()
    db.refresh(medication)
    return medication


def show_medication(db: Session, medication_id: uuid.UUID, user: User) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    _professional(db, medication, user)
    if medication.hidden_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta medicação já está visível para o paciente.")
    medication.hidden_by_staff_id = medication.hidden_at = medication.hidden_reason = None
    db.commit()
    db.refresh(medication)
    return medication


def delete_medication(
    db: Session, medication_id: uuid.UUID, payload: MedicationDeleteRequest, user: User
) -> Medication:
    medication = get_medication(db, medication_id, user, lock=True)
    reason = (payload.reason or "").strip() or None
    if user.role == UserRole.PATIENT:
        if not is_own_open_declaration(medication, user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PATIENT_LOCKED)
    else:
        _professional(db, medication, user)
        if reason is None:
            raise _field_error("reason", "Indica o motivo da remoção.")
    medication.deleted_at, medication.deleted_by_user_id, medication.deletion_reason = (
        datetime.now(UTC),
        user.id,
        reason,
    )
    db.commit()
    db.refresh(medication)
    return medication
