import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event, record_denied_access
from app.core.client_ip import get_client_ip
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AppointmentType, AuditAction, AuditResult, ScheduleAbsence, User, UserRole
from app.modules.appointments.schemas import AppointmentPatientView
from app.modules.appointments.views import patient_views
from app.modules.scheduling import bookings, changes, service
from app.modules.scheduling.audit import audit_auto_assignment, audit_released_assignment, audit_scheduling
from app.modules.scheduling.availability import TZ, free_slots, patient_busy_intervals
from app.modules.scheduling.eligibility import bookable_professionals, own_patient
from app.modules.scheduling.schemas import (
    AbsenceIn,
    AbsenceOut,
    AgendaAppointment,
    AgendaOut,
    AppointmentTypeCreate,
    AppointmentTypeOut,
    AppointmentTypeUpdate,
    BookableProfessional,
    BookingIn,
    BookingSettingsOut,
    BookingSettingsUpdate,
    ProfessionalOut,
    ProfessionalUpdate,
    RescheduleIn,
    ScheduleRuleOut,
    SlotOut,
    SpecialtyCreate,
    SpecialtyOut,
    SpecialtyUpdate,
    WeeklyScheduleIn,
)

router = APIRouter()


@contextmanager
def _denials(request: Request, user: User, resource_type: str, resource_id: object) -> Iterator[None]:
    try:
        yield
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            record_denied_access(request, user, resource_type, str(resource_id))
        raise


def _settings_out(db: Session, clinic_id: object) -> BookingSettingsOut:
    settings = service.get_settings(db, clinic_id)  # type: ignore[arg-type]
    phone, address = service.clinic_contact(db, clinic_id)  # type: ignore[arg-type]
    return BookingSettingsOut(
        cancellation_deadline_hours=settings.cancellation_deadline_hours,
        waitlist_offer_minutes=settings.waitlist_offer_minutes,
        reminder_hours_before=settings.reminder_hours_before,
        booking_horizon_days=settings.booking_horizon_days,
        clinic_phone=phone,
        clinic_address=address,
    )


def _absence_out(absence: ScheduleAbsence, conflicts: int = 0) -> AbsenceOut:
    return AbsenceOut(
        id=absence.id,
        staff_id=absence.staff_id,
        starts_at=absence.starts_at,
        ends_at=absence.ends_at,
        kind=absence.kind,
        conflicting_appointments=conflicts,
    )


# --- specialties --------------------------------------------------------------------------------


@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[SpecialtyOut]:
    return [SpecialtyOut.model_validate(row) for row in service.list_specialties(db, user)]


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
def create_specialty(
    payload: SpecialtyCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SpecialtyOut:
    with _denials(request, user, "specialty", "new"):
        specialty = service.create_specialty(db, payload, user)
    audit_scheduling(request, user, AuditAction.SPECIALTY_CREATED, "specialty", specialty.id)
    return SpecialtyOut.model_validate(specialty)


@router.patch("/specialties/{specialty_id}", response_model=SpecialtyOut)
def update_specialty(
    specialty_id: uuid.UUID,
    payload: SpecialtyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SpecialtyOut:
    with _denials(request, user, "specialty", specialty_id):
        specialty = service.update_specialty(db, specialty_id, payload, user)
    audit_scheduling(request, user, AuditAction.SPECIALTY_UPDATED, "specialty", specialty.id)
    return SpecialtyOut.model_validate(specialty)


# --- appointment types ------------------------------------------------------------------------


@router.get("/appointment-types", response_model=list[AppointmentTypeOut])
def list_types(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[AppointmentTypeOut]:
    return [AppointmentTypeOut.model_validate(row) for row in service.list_types(db, user)]


@router.post("/appointment-types", response_model=AppointmentTypeOut, status_code=201)
def create_type(
    payload: AppointmentTypeCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AppointmentTypeOut:
    with _denials(request, user, "appointment_type", "new"):
        appointment_type = service.create_type(db, payload, user)
    audit_scheduling(request, user, AuditAction.APPOINTMENT_TYPE_CREATED, "appointment_type", appointment_type.id)
    return AppointmentTypeOut.model_validate(appointment_type)


@router.patch("/appointment-types/{type_id}", response_model=AppointmentTypeOut)
def update_type(
    type_id: uuid.UUID,
    payload: AppointmentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AppointmentTypeOut:
    with _denials(request, user, "appointment_type", type_id):
        appointment_type = service.update_type(db, type_id, payload, user)
    audit_scheduling(request, user, AuditAction.APPOINTMENT_TYPE_UPDATED, "appointment_type", appointment_type.id)
    return AppointmentTypeOut.model_validate(appointment_type)


# --- clinic settings --------------------------------------------------------------------------


@router.get("/settings", response_model=BookingSettingsOut)
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BookingSettingsOut:
    return _settings_out(db, user.clinic_id)


@router.patch("/settings", response_model=BookingSettingsOut)
def update_settings(
    payload: BookingSettingsUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> BookingSettingsOut:
    with _denials(request, user, "booking_settings", user.clinic_id):
        service.update_settings(db, payload, user)
    audit_scheduling(request, user, AuditAction.BOOKING_SETTINGS_UPDATED, "booking_settings", user.clinic_id)
    return _settings_out(db, user.clinic_id)


# --- professionals and weekly schedules -----------------------------------------------------------


@router.get("/professionals", response_model=list[ProfessionalOut])
def list_professionals(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ProfessionalOut]:
    with _denials(request, user, "professional_list", user.clinic_id):
        rows = service.list_professionals(db, user)
    return [
        ProfessionalOut(
            id=staff.id,
            full_name=name,
            staff_role=staff.staff_role.value,
            specialty_id=staff.specialty_id,
            accepts_new_patients=staff.accepts_new_patients,
        )
        for staff, name in rows
    ]


@router.patch("/professionals/{staff_id}", response_model=ProfessionalOut)
def update_professional(
    staff_id: uuid.UUID,
    payload: ProfessionalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfessionalOut:
    with _denials(request, user, "professional", staff_id):
        staff = service.update_professional(db, staff_id, payload, user)
    audit_scheduling(request, user, AuditAction.STAFF_BOOKING_PROFILE_UPDATED, "staff", staff.id)
    return ProfessionalOut(
        id=staff.id,
        full_name=staff.user.full_name,
        staff_role=staff.staff_role.value,
        specialty_id=staff.specialty_id,
        accepts_new_patients=staff.accepts_new_patients,
    )


def _rules_out(db: Session, staff: object) -> list[ScheduleRuleOut]:
    return [
        ScheduleRuleOut(
            id=rule.id,
            weekday=rule.weekday,
            start_time=rule.start_time,
            end_time=rule.end_time,
            valid_from=rule.valid_from,
            valid_until=rule.valid_until,
            appointment_type_ids=type_ids,
        )
        for rule, type_ids in service.rules_of(db, staff)  # type: ignore[arg-type]
    ]


@router.get("/professionals/{staff_id}/schedule", response_model=list[ScheduleRuleOut])
def get_schedule(
    staff_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ScheduleRuleOut]:
    with _denials(request, user, "schedule", staff_id):
        staff = service.agenda_professional(db, staff_id, user)
    return _rules_out(db, staff)


@router.post("/professionals/{staff_id}/schedule", response_model=list[ScheduleRuleOut])
def replace_schedule(
    staff_id: uuid.UUID,
    payload: WeeklyScheduleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScheduleRuleOut]:
    with _denials(request, user, "schedule", staff_id):
        staff = service.replace_schedule(db, staff_id, payload.rules, user)
    audit_scheduling(request, user, AuditAction.SCHEDULE_UPDATED, "schedule", staff.id, count=len(payload.rules))
    return _rules_out(db, staff)


# --- absences and agenda ------------------------------------------------------------------------


@router.post("/absences", response_model=AbsenceOut, status_code=201)
def add_absence(
    payload: AbsenceIn,
    request: Request,
    staff_id: uuid.UUID | None = Query(default=None, description="Schedulers only; default: oneself"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AbsenceOut:
    with _denials(request, user, "absence", staff_id or "own"):
        absence, conflicts = service.add_absence(db, staff_id, payload, user)
    audit_scheduling(request, user, AuditAction.ABSENCE_CREATED, "absence", absence.id, staff_id=absence.staff_id)
    return _absence_out(absence, conflicts)


@router.post("/absences/{absence_id}/delete", status_code=204)
def delete_absence(
    absence_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    with _denials(request, user, "absence", absence_id):
        absence = service.delete_absence(db, absence_id, user)
    audit_scheduling(request, user, AuditAction.ABSENCE_DELETED, "absence", absence_id, staff_id=absence.staff_id)
    return Response(status_code=204)


@router.get("/agenda", response_model=AgendaOut)
def agenda(
    request: Request,
    day_from: date = Query(alias="from"),
    day_to: date = Query(alias="to"),
    staff_id: uuid.UUID | None = Query(default=None, description="Schedulers only; default: oneself"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgendaOut:
    service.check_range(day_from, day_to)
    with _denials(request, user, "agenda", staff_id or "own"):
        staff = service.agenda_professional(db, staff_id, user)
    return AgendaOut(
        staff_id=staff.id,
        appointments=[
            AgendaAppointment(
                id=appointment.id,
                scheduled_at=appointment.scheduled_at,
                ends_at=appointment.ends_at,
                status=appointment.status,
                patient_name=patient_name,
                appointment_type=type_name,
            )
            for appointment, patient_name, type_name in service.agenda_appointments(db, staff, day_from, day_to)
        ],
        absences=[_absence_out(absence) for absence in service.absences_between(db, staff, day_from, day_to)],
        rules=_rules_out(db, staff),
    )


# --- free slots -----------------------------------------------------------------------------


@router.get("/slots", response_model=list[SlotOut])
def slots(
    appointment_type_id: uuid.UUID,
    day_from: date = Query(alias="from"),
    day_to: date = Query(alias="to"),
    staff_id: uuid.UUID | None = Query(default=None, description="Omit for 'Qualquer disponível'"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SlotOut]:
    """Free slots of one professional, or of every eligible professional ("Qualquer disponível")."""
    service.check_range(day_from, day_to)
    patient = own_patient(db, user) if user.role == UserRole.PATIENT else None
    appointment_type: AppointmentType = service.get_type(
        db, appointment_type_id, user.clinic_id, active_only=user.role == UserRole.PATIENT
    )
    if patient is not None:
        settings = service.get_settings(db, user.clinic_id)
        today = datetime.now(TZ).date()
        day_from = max(day_from, today)
        day_to = min(day_to, today + timedelta(days=settings.booking_horizon_days))
    eligible = bookable_professionals(
        db, clinic_id=user.clinic_id, appointment_type_id=appointment_type.id, patient=patient
    )
    names = {staff.id: name for staff, name, _known in eligible}
    staff_ids = [staff_id] if staff_id is not None else list(names)
    if staff_id is not None and staff_id not in names:
        return []
    found = free_slots(
        db,
        clinic_id=user.clinic_id,  # type: ignore[arg-type]
        appointment_type=appointment_type,
        staff_ids=staff_ids,
        day_from=day_from,
        day_to=day_to,
    )
    if patient is not None:
        # Never offer a time the patient is already booked at (it would only end in a 409).
        busy = patient_busy_intervals(db, patient.id, found)
        found = [slot for slot in found if not any(start < slot.ends_at and end > slot.starts_at for start, end in busy)]
    return [
        SlotOut(starts_at=slot.starts_at, ends_at=slot.ends_at, staff_id=slot.staff_id, staff_name=names[slot.staff_id])
        for slot in found
    ]


# --- patient booking ----------------------------------------------------------------------------


@router.get("/bookable-professionals", response_model=list[BookableProfessional])
def bookable_professionals_for_type(
    appointment_type_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[BookableProfessional]:
    """Professionals with a schedule for this type; for a patient, known ones first and
    without those who do not accept new patients (unless already known)."""
    return [
        BookableProfessional(id=staff.id, full_name=name, known=known)
        for staff, name, known in bookings.bookable_for_patient(db, user, appointment_type_id)
    ]


@router.post("/bookings", response_model=AppointmentPatientView, status_code=201)
def book(
    payload: BookingIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AppointmentPatientView:
    if user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Só pacientes marcam consultas aqui.")
    with _denials(request, user, "appointment", "booking"):
        appointment, assignment = bookings.book_for_patient(db, user, payload)
    record_audit_event(
        action=AuditAction.APPOINTMENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"patient_id": appointment.patient_id, "staff_id": appointment.staff_id, "via": "patient"},
    )
    audit_auto_assignment(request, user, assignment, appointment.id)
    return patient_views(db, [appointment])[0]


# --- the patient changes their own appointment (step 5) --------------------------------------


def _audit_appointment(request: Request, user: User, action: AuditAction, appointment_id: object, **ids: object) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=appointment_id,  # type: ignore[arg-type]
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={key: str(value) for key, value in ids.items()},
    )


@router.post("/bookings/{appointment_id}/cancel", response_model=AppointmentPatientView)
def cancel_own(
    appointment_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AppointmentPatientView:
    """The patient cancels their own appointment before the clinic's deadline (409 after
    it, or if it is no longer active). The slot is free at once."""
    with _denials(request, user, "appointment", appointment_id):
        appointment, ended = changes.cancel_by_patient(db, user, appointment_id)
    _audit_appointment(request, user, AuditAction.APPOINTMENT_CANCELLED, appointment.id, patient_id=appointment.patient_id, via="patient")
    audit_released_assignment(request, user, ended, appointment.id, via="appointment_cancelled")
    return patient_views(db, [appointment])[0]


@router.get("/bookings/{appointment_id}/slots", response_model=list[SlotOut])
def reschedule_slots(
    appointment_id: uuid.UUID,
    request: Request,
    day_from: date = Query(alias="from"),
    day_to: date = Query(alias="to"),
    professional: Literal["same", "any"] = "same",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SlotOut]:
    """Free slots to move the patient's appointment to, with the same professional or any."""
    with _denials(request, user, "appointment", appointment_id):
        found = changes.reschedule_slots(db, user, appointment_id, day_from, day_to, same_professional=professional == "same")
    return [
        SlotOut(starts_at=slot.starts_at, ends_at=slot.ends_at, staff_id=slot.staff_id, staff_name=name) for slot, name in found
    ]


@router.post("/bookings/{appointment_id}/reschedule", response_model=AppointmentPatientView, status_code=201)
def reschedule_own(
    appointment_id: uuid.UUID,
    payload: RescheduleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AppointmentPatientView:
    """Move the patient's appointment to a free slot: the old one is cancelled and the new
    one booked together (409, nothing changed, if the slot was taken meanwhile). Returns the
    new appointment."""
    with _denials(request, user, "appointment", appointment_id):
        new, old, created, ended = changes.reschedule_by_patient(
            db, user, appointment_id, starts_at=payload.starts_at, staff_id=payload.staff_id
        )
    _audit_appointment(request, user, AuditAction.APPOINTMENT_RESCHEDULED, old.id, new_appointment_id=new.id)
    _audit_appointment(
        request, user, AuditAction.APPOINTMENT_CREATED, new.id, patient_id=new.patient_id, staff_id=new.staff_id, via="patient"
    )
    audit_released_assignment(request, user, ended, old.id, via="appointment_moved")
    audit_auto_assignment(request, user, created, new.id)
    return patient_views(db, [new])[0]
