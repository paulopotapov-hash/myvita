"""
Patient appointment requests.

A request is open while PENDING (waiting for the clinic) or PROPOSED (the clinic
proposed a time, waiting for the patient). Every change locks the request row
(SELECT ... FOR UPDATE), so two concurrent decisions on one request never both win:
the second one sees a request that is no longer open and gets 409.

Booking from a request (staff acceptance, or the patient accepting a proposal) goes
through the scheduling service (clinic advisory lock, tenant and overlap checks, the
database exclusion constraints) in the SAME transaction as the request change, so
nothing is half-written. A proposal does not hold the slot: if it was taken before the
patient accepts, the acceptance fails with 409, the proposal is cleared and the request
goes back to PENDING (the schedulers are told), so the clinic proposes another time.

A reschedule request (`reschedule_of_id`) moves one of the patient's appointments: the
old one is cancelled in the same transaction that books the new one.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    OPEN_REQUEST_STATUSES,
    Appointment,
    AppointmentRequest,
    AppointmentRequestStatus,
    AppointmentStatus,
    AppointmentType,
    BookingMode,
    ClinicalCareAssignment,
    Patient,
    Specialty,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.appointment_requests.schemas import (
    AppointmentRequestAccept,
    AppointmentRequestCreate,
    AppointmentRequestPropose,
)
from app.modules.appointments.schemas import AppointmentCreateRequest
from app.modules.appointments.service import create_appointment_from_request
from app.modules.notifications.events import NotificationEvent, notify
from app.modules.scheduling import changes
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.availability import TZ
from app.modules.scheduling.booking import CLINICAL_ROLES, AutoAssignment
from app.modules.scheduling.eligibility import bookable_professionals

MAX_PENDING_PER_PATIENT = 5
_NOT_FOUND = "Pedido de consulta não encontrado."
PROPOSAL_TAKEN = "O horário proposto já não está disponível. A clínica vai propor outro."
ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
DEFAULT_DURATION_MINUTES = 30


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _not_pending() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O pedido já foi processado.")


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def own_patient(db: Session, user: User) -> Patient:
    patient = (
        db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil de paciente não encontrado.")
    return patient


def _notify_schedulers(db: Session, clinic_id: uuid.UUID, event: NotificationEvent, dedupe_key: str | None) -> None:
    """Scheduling roles of the clinic: clinic admins and administrative staff. Generic text
    only: notifications never carry the request reason."""
    schedulers = (
        db.query(User.id)
        .outerjoin(Staff, Staff.user_id == User.id)
        .filter(
            User.clinic_id == clinic_id,
            User.is_active.is_(True),
            (User.role == UserRole.CLINIC_ADMIN)
            | ((User.role == UserRole.STAFF) & (Staff.staff_role == StaffRole.ADMIN)),
        )
        .all()
    )
    for (scheduler_id,) in schedulers:
        notify(db, event, clinic_id=clinic_id, recipient_user_id=scheduler_id, dedupe_key=dedupe_key)


def _check_window(db: Session, patient: Patient, payload: AppointmentRequestCreate) -> None:
    now = datetime.now(UTC)
    if payload.preferred_start is not None and payload.preferred_start <= now:
        raise _unprocessable("Escolha uma data futura.")
    if payload.preferred_from is not None:
        today = now.astimezone(TZ).date()
        horizon = scheduling.get_settings(db, patient.clinic_id).booking_horizon_days
        if payload.preferred_from < today:
            raise _unprocessable("Escolhe datas a partir de hoje.")
        if (payload.preferred_to or payload.preferred_from) > today + timedelta(days=horizon):
            raise _unprocessable(f"Escolhe datas nos próximos {horizon} dias.")


def _reschedule_target(db: Session, patient: Patient, appointment_id: uuid.UUID) -> Appointment:
    appointment = changes.own_appointment(db, patient, appointment_id)
    changes.require_changeable(db, appointment)
    already = (
        db.query(AppointmentRequest.id)
        .filter(
            AppointmentRequest.reschedule_of_id == appointment.id,
            AppointmentRequest.status.in_(OPEN_REQUEST_STATUSES),
        )
        .first()
    )
    if already is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já pediste para remarcar esta consulta.")
    return appointment


def create_request(db: Session, user: User, payload: AppointmentRequestCreate) -> AppointmentRequest:
    patient = own_patient(db, user)
    _check_window(db, patient, payload)
    open_requests = (
        db.query(AppointmentRequest)
        .filter(
            AppointmentRequest.patient_id == patient.id,
            AppointmentRequest.status.in_(OPEN_REQUEST_STATUSES),
        )
        .count()
    )
    if open_requests >= MAX_PENDING_PER_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tem demasiados pedidos pendentes. Aguarde a resposta da clínica.",
        )
    type_id = payload.appointment_type_id
    reschedule_of = None
    if payload.reschedule_of_id is not None:
        reschedule_of = _reschedule_target(db, patient, payload.reschedule_of_id)
        type_id = reschedule_of.appointment_type_id
    elif type_id is not None:
        appointment_type = scheduling.get_type(db, type_id, patient.clinic_id, active_only=True)
        if appointment_type.booking_mode == BookingMode.DIRECT:
            raise _unprocessable("Este tipo de consulta marca-se diretamente: escolhe um horário livre.")
    if payload.staff_id is not None:
        if type_id is None:
            raise _unprocessable("Escolhe o tipo de consulta para indicar um profissional.")
        eligible = {staff.id for staff, _name, _known in bookable_professionals(
            db, clinic_id=patient.clinic_id, appointment_type_id=type_id, patient=patient
        )}
        if payload.staff_id not in eligible:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não disponível.")

    request = AppointmentRequest(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        preferred_start=payload.preferred_start,
        preferred_from=payload.preferred_from,
        preferred_to=payload.preferred_to,
        preferred_weekdays=payload.preferred_weekdays,
        preferred_period=payload.preferred_period,
        appointment_type_id=type_id,
        staff_id=payload.staff_id,
        reschedule_of_id=reschedule_of.id if reschedule_of is not None else None,
        reason=payload.reason if reschedule_of is None else (payload.reason or reschedule_of.reason),
    )
    db.add(request)
    db.flush()
    _notify_schedulers(db, patient.clinic_id, NotificationEvent.APPOINTMENT_REQUEST_RECEIVED, str(request.id))
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


def _lock_own(db: Session, request_id: uuid.UUID, user: User) -> AppointmentRequest:
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
    return request


def _duration(db: Session, request: AppointmentRequest, given: int | None) -> int:
    if given is not None:
        return given
    if request.appointment_type_id is not None:
        appointment_type = db.get(AppointmentType, request.appointment_type_id)
        if appointment_type is not None:
            return appointment_type.duration_minutes
    return DEFAULT_DURATION_MINUTES


def _book(
    db: Session,
    request: AppointmentRequest,
    actor: User,
    *,
    staff_id: uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int,
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
    """Create the request's appointment and mark the request accepted, in one commit."""
    request.status = AppointmentRequestStatus.ACCEPTED
    request.decided_by_user_id = actor.id
    request.decided_at = datetime.now(UTC)
    replaces = db.get(Appointment, request.reschedule_of_id) if request.reschedule_of_id is not None else None

    def link(appointment: Appointment) -> None:
        request.appointment_id = appointment.id

    return create_appointment_from_request(
        db,
        str(request.clinic_id),
        AppointmentCreateRequest(
            patient_id=request.patient_id,
            staff_id=staff_id,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            reason=request.reason,
        ),
        actor.id,
        appointment_type_id=request.appointment_type_id,
        replaces=replaces,
        before_commit=link,
    )


def accept_request(
    db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID, actor: User, payload: AppointmentRequestAccept
) -> tuple[AppointmentRequest, Appointment, AutoAssignment | None, AutoAssignment | None]:
    request = _lock_for_clinic(db, request_id, clinic_id)
    if request.status != AppointmentRequestStatus.PENDING:
        raise _not_pending()
    patient = db.get(Patient, request.patient_id)
    if patient is None:
        raise _not_found()
    notify(
        db,
        NotificationEvent.APPOINTMENT_REQUEST_ACCEPTED,
        clinic_id=patient.clinic_id,
        recipient_user_id=patient.user_id,
        dedupe_key=str(request.id),
    )
    appointment, created, ended = _book(
        db,
        request,
        actor,
        staff_id=payload.staff_id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=_duration(db, request, payload.duration_minutes),
    )
    db.refresh(request)
    return request, appointment, created, ended


def propose_request(
    db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID, actor: User, payload: AppointmentRequestPropose
) -> AppointmentRequest:
    """The clinic proposes a time with a professional; the slot is checked now (409 if it is
    already taken) but not held: the patient's acceptance books it."""
    request = _lock_for_clinic(db, request_id, clinic_id)
    if request.status != AppointmentRequestStatus.PENDING:
        raise _not_pending()
    patient = db.get(Patient, request.patient_id)
    if patient is None:
        raise _not_found()
    staff = db.get(Staff, payload.staff_id)
    if staff is None or staff.clinic_id != clinic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado nesta clínica.")
    if staff.staff_role not in CLINICAL_ROLES:
        raise _unprocessable("Escolhe um profissional de saúde.")
    if payload.scheduled_at <= datetime.now(UTC):
        raise _unprocessable("Escolha uma data futura.")
    duration = _duration(db, request, payload.duration_minutes)
    ends_at = payload.scheduled_at + timedelta(minutes=duration)
    busy = (
        db.query(Appointment.patient_id)
        .filter(
            Appointment.clinic_id == clinic_id,
            (Appointment.staff_id == staff.id) | (Appointment.patient_id == patient.id),
            Appointment.status.in_(ACTIVE),
            Appointment.scheduled_at < ends_at,
            Appointment.ends_at > payload.scheduled_at,
        )
    )
    if request.reschedule_of_id is not None:
        busy = busy.filter(Appointment.id != request.reschedule_of_id)
    taken = busy.first()
    if taken is not None:
        detail = "O paciente já tem uma consulta a essa hora." if taken[0] == patient.id else "Este horário já não está disponível para este profissional."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    request.status = AppointmentRequestStatus.PROPOSED
    request.proposed_staff_id = staff.id
    request.proposed_start = payload.scheduled_at
    request.proposed_duration_minutes = duration
    request.proposed_at = datetime.now(UTC)
    request.proposed_by_user_id = actor.id
    notify(
        db,
        NotificationEvent.APPOINTMENT_REQUEST_PROPOSED,
        clinic_id=clinic_id,
        recipient_user_id=patient.user_id,
        dedupe_key=f"{request.id}:{request.proposed_at.isoformat()}",
    )
    db.commit()
    db.refresh(request)
    return request


def accept_proposal(
    db: Session, request_id: uuid.UUID, user: User
) -> tuple[AppointmentRequest, Appointment, AutoAssignment | None, AutoAssignment | None]:
    request = _lock_own(db, request_id, user)
    if request.status != AppointmentRequestStatus.PROPOSED:
        raise _not_pending()
    assert request.proposed_staff_id and request.proposed_start and request.proposed_duration_minutes
    if request.proposed_start <= datetime.now(UTC):
        _reopen(db, request)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PROPOSAL_TAKEN)
    _notify_schedulers(db, request.clinic_id, NotificationEvent.APPOINTMENT_REQUEST_ANSWERED, None)
    try:
        appointment, created, ended = _book(
            db,
            request,
            user,
            staff_id=request.proposed_staff_id,
            scheduled_at=request.proposed_start,
            duration_minutes=request.proposed_duration_minutes,
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise
        db.rollback()
        _reopen(db, _lock_own(db, request_id, user))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PROPOSAL_TAKEN) from exc
    db.refresh(request)
    return request, appointment, created, ended


def _reopen(db: Session, request: AppointmentRequest) -> None:
    """The proposed slot is gone: back to PENDING, without the proposal; schedulers are told."""
    proposed_at = request.proposed_at
    request.status = AppointmentRequestStatus.PENDING
    request.proposed_staff_id = request.proposed_start = request.proposed_duration_minutes = None
    request.proposed_at = request.proposed_by_user_id = None
    _notify_schedulers(
        db,
        request.clinic_id,
        NotificationEvent.APPOINTMENT_REQUEST_REOPENED,
        f"{request.id}:{proposed_at.isoformat() if proposed_at else ''}",
    )
    db.commit()


def decline_proposal(db: Session, request_id: uuid.UUID, user: User) -> AppointmentRequest:
    request = _lock_own(db, request_id, user)
    if request.status != AppointmentRequestStatus.PROPOSED:
        raise _not_pending()
    request.status = AppointmentRequestStatus.DECLINED
    request.decided_by_user_id = user.id
    request.decided_at = datetime.now(UTC)
    _notify_schedulers(db, request.clinic_id, NotificationEvent.APPOINTMENT_REQUEST_ANSWERED, None)
    db.commit()
    db.refresh(request)
    return request


def reject_request(db: Session, request_id: uuid.UUID, clinic_id: uuid.UUID, actor: User) -> AppointmentRequest:
    """Refuse a pending request, or withdraw a proposal the patient has not answered."""
    request = _lock_for_clinic(db, request_id, clinic_id)
    if request.status not in OPEN_REQUEST_STATUSES:
        raise _not_pending()
    patient = db.get(Patient, request.patient_id)
    if patient is None:
        raise _not_found()
    request.status = AppointmentRequestStatus.REJECTED
    request.decided_by_user_id = actor.id
    request.decided_at = datetime.now(UTC)
    notify(
        db,
        NotificationEvent.APPOINTMENT_REQUEST_REJECTED,
        clinic_id=patient.clinic_id,
        recipient_user_id=patient.user_id,
        dedupe_key=str(request.id),
    )
    db.commit()
    db.refresh(request)
    return request


def cancel_own_request(db: Session, request_id: uuid.UUID, user: User) -> AppointmentRequest:
    request = _lock_own(db, request_id, user)
    if request.status not in OPEN_REQUEST_STATUSES:
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


def display_names(
    db: Session, requests: list[AppointmentRequest]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, tuple[str, str | None]], dict[uuid.UUID, datetime]]:
    """(professional names, (type, specialty) names, start of the appointments to move)."""
    staff_ids = {staff_id for request in requests for staff_id in (request.staff_id, request.proposed_staff_id) if staff_id}
    type_ids = {request.appointment_type_id for request in requests if request.appointment_type_id}
    moved_ids = {request.reschedule_of_id for request in requests if request.reschedule_of_id}
    names: dict[uuid.UUID, str] = {}
    if staff_ids:
        names = {
            staff_id: name
            for staff_id, name in db.query(Staff.id, User.full_name).join(User, User.id == Staff.user_id).filter(Staff.id.in_(staff_ids))
        }
    types: dict[uuid.UUID, tuple[str, str | None]] = {}
    if type_ids:
        types = {
            type_id: (type_name, specialty_name)
            for type_id, type_name, specialty_name in db.query(AppointmentType.id, AppointmentType.name, Specialty.name)
            .join(Specialty, Specialty.id == AppointmentType.specialty_id)
            .filter(AppointmentType.id.in_(type_ids))
        }
    starts: dict[uuid.UUID, datetime] = {}
    if moved_ids:
        starts = {
            appointment_id: start
            for appointment_id, start in db.query(Appointment.id, Appointment.scheduled_at).filter(Appointment.id.in_(moved_ids))
        }
    return names, types, starts
