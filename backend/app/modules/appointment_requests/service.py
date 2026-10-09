"""
Patient appointment requests.

Only PENDING requests change state. Acceptance locks the request row
(SELECT ... FOR UPDATE) and creates the appointment through the existing
scheduling service (clinic advisory lock + overlap and tenant checks) in the
SAME transaction, so a concurrent second acceptance waits, then sees a
non-pending request and gets 409 — never a second appointment.
"""
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentRequest,
    AppointmentRequestStatus,
    ClinicalCareAssignment,
    Notification,
    Patient,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.appointment_requests.schemas import AppointmentRequestAccept, AppointmentRequestCreate
from app.modules.appointments.schemas import AppointmentCreateRequest
from app.modules.appointments.service import create_appointment

MAX_PENDING_PER_PATIENT = 5
_NOT_FOUND = "Pedido de consulta não encontrado."


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _not_pending() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O pedido já foi processado.")


def _notify(db: Session, clinic_id: uuid.UUID, user_id: uuid.UUID, title: str, message: str) -> None:
    # Generic text only: notifications never carry the request reason.
    db.add(Notification(clinic_id=clinic_id, user_id=user_id, title=title, message=message))


def own_patient(db: Session, user: User) -> Patient:
    patient = (
        db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil de paciente não encontrado.")
    return patient


def create_request(db: Session, user: User, payload: AppointmentRequestCreate) -> AppointmentRequest:
    patient = own_patient(db, user)
    if payload.preferred_start <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Escolha uma data futura."
        )
    pending = (
        db.query(AppointmentRequest)
        .filter(
            AppointmentRequest.patient_id == patient.id,
            AppointmentRequest.status == AppointmentRequestStatus.PENDING,
        )
        .count()
    )
    if pending >= MAX_PENDING_PER_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tem demasiados pedidos pendentes. Aguarde a resposta da clínica.",
        )
    request = AppointmentRequest(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        preferred_start=payload.preferred_start,
        reason=payload.reason,
    )
    db.add(request)
    # Scheduling roles of the clinic: clinic admins and administrative staff.
    schedulers = (
        db.query(User.id)
        .outerjoin(Staff, Staff.user_id == User.id)
        .filter(
            User.clinic_id == patient.clinic_id,
            User.is_active.is_(True),
            (User.role == UserRole.CLINIC_ADMIN)
            | ((User.role == UserRole.STAFF) & (Staff.staff_role == StaffRole.ADMIN)),
        )
        .all()
    )
    for (scheduler_id,) in schedulers:
        _notify(
            db,
            patient.clinic_id,
            scheduler_id,
            "Novo pedido de consulta",
            "Um paciente pediu uma consulta. Reveja os pedidos pendentes.",
        )
    db.commit()
    db.refresh(request)
    return request


def _with_names(db: Session, query: object, offset: int, limit: int) -> tuple[list[tuple[AppointmentRequest, str]], int]:
    total = query.count()  # type: ignore[attr-defined]
    rows = (
        query.order_by(AppointmentRequest.created_at.desc(), AppointmentRequest.id.desc())  # type: ignore[attr-defined]
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [(row[0], row[1]) for row in rows], total


def list_for_patient(
    db: Session, user: User, *, offset: int, limit: int
) -> tuple[list[tuple[AppointmentRequest, str]], int]:
    patient = own_patient(db, user)
    query = (
        db.query(AppointmentRequest, User.full_name)
        .join(Patient, Patient.id == AppointmentRequest.patient_id)
        .join(User, User.id == Patient.user_id)
        .filter(AppointmentRequest.patient_id == patient.id, AppointmentRequest.clinic_id == patient.clinic_id)
    )
    return _with_names(db, query, offset, limit)


def list_for_clinic(
    db: Session,
    clinic_id: uuid.UUID,
    request_status: AppointmentRequestStatus | None,
    *,
    offset: int,
    limit: int,
    assigned_to_staff_id: uuid.UUID | None = None,
) -> tuple[list[tuple[AppointmentRequest, str]], int]:
    """`assigned_to_staff_id` restricts the listing to patients on that professional's
    active care team (clinicians); schedulers pass None and see the whole clinic."""
    query = (
        db.query(AppointmentRequest, User.full_name)
        .join(Patient, Patient.id == AppointmentRequest.patient_id)
        .join(User, User.id == Patient.user_id)
        .filter(AppointmentRequest.clinic_id == clinic_id)
    )
    if request_status is not None:
        query = query.filter(AppointmentRequest.status == request_status)
    if assigned_to_staff_id is not None:
        assigned_patient_ids = db.query(ClinicalCareAssignment.patient_id).filter(
            ClinicalCareAssignment.clinic_id == clinic_id,
            ClinicalCareAssignment.staff_id == assigned_to_staff_id,
            ClinicalCareAssignment.active.is_(True),
        )
        query = query.filter(AppointmentRequest.patient_id.in_(assigned_patient_ids))
    return _with_names(db, query, offset, limit)


def request_patient_id(db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID) -> uuid.UUID:
    """Patient of a request in the caller's clinic, or 404 (never reveals other clinics' requests)."""
    patient_id = (
        db.query(AppointmentRequest.patient_id)
        .filter(AppointmentRequest.id == request_id, AppointmentRequest.clinic_id == clinic_id)
        .scalar()
    )
    if patient_id is None:
        raise _not_found()
    return patient_id


def _lock_for_clinic(db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID) -> AppointmentRequest:
    request = (
        db.query(AppointmentRequest)
        .filter(AppointmentRequest.id == request_id, AppointmentRequest.clinic_id == clinic_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise _not_found()
    return request


def accept_request(
    db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID, actor: User, payload: AppointmentRequestAccept
) -> tuple[AppointmentRequest, Appointment]:
    request = _lock_for_clinic(db, request_id, clinic_id)
    if request.status != AppointmentRequestStatus.PENDING:
        raise _not_pending()
    patient = db.get(Patient, request.patient_id)
    if patient is None:
        raise _not_found()
    request.status = AppointmentRequestStatus.ACCEPTED
    request.decided_by_user_id = actor.id
    request.decided_at = datetime.now(UTC)
    _notify(
        db,
        patient.clinic_id,
        patient.user_id,
        "Pedido de consulta aceite",
        "O seu pedido de consulta foi aceite e a consulta foi marcada.",
    )
    # Existing scheduling path: clinic advisory lock, staff/patient tenant
    # checks and overlap detection. It commits the request change, the
    # notifications and the appointment together; any error rolls all back.
    appointment = create_appointment(
        db,
        str(clinic_id),
        AppointmentCreateRequest(
            patient_id=request.patient_id,
            staff_id=payload.staff_id,
            scheduled_at=payload.scheduled_at,
            duration_minutes=payload.duration_minutes,
            reason=request.reason,
        ),
    )
    request.appointment_id = appointment.id
    db.commit()
    db.refresh(request)
    return request, appointment


def reject_request(db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID, actor: User) -> AppointmentRequest:
    request = _lock_for_clinic(db, request_id, clinic_id)
    if request.status != AppointmentRequestStatus.PENDING:
        raise _not_pending()
    patient = db.get(Patient, request.patient_id)
    if patient is None:
        raise _not_found()
    request.status = AppointmentRequestStatus.REJECTED
    request.decided_by_user_id = actor.id
    request.decided_at = datetime.now(UTC)
    _notify(
        db,
        patient.clinic_id,
        patient.user_id,
        "Pedido de consulta recusado",
        "O seu pedido de consulta não pôde ser aceite. Contacte a clínica se precisar.",
    )
    db.commit()
    db.refresh(request)
    return request


def cancel_own_request(db: Session, request_id: uuid.UUID, user: User) -> AppointmentRequest:
    patient = own_patient(db, user)
    request = (
        db.query(AppointmentRequest)
        .filter(
            AppointmentRequest.id == request_id,
            AppointmentRequest.patient_id == patient.id,
            AppointmentRequest.clinic_id == patient.clinic_id,
        )
        .with_for_update()
        .first()
    )
    if request is None:
        raise _not_found()
    if request.status != AppointmentRequestStatus.PENDING:
        raise _not_pending()
    request.status = AppointmentRequestStatus.CANCELLED
    request.decided_by_user_id = user.id
    request.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(request)
    return request


def patient_name(db: Session, request: AppointmentRequest) -> str:
    row = (
        db.query(User.full_name)
        .join(Patient, Patient.user_id == User.id)
        .filter(Patient.id == request.patient_id)
        .first()
    )
    return row[0] if row else ""
