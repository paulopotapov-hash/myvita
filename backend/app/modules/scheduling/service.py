"""Scheduling configuration and agendas.

Who may do what (always within the caller's own clinic; other clinics' rows are 404):
- schedulers (clinic administrator, administrative staff): specialties, appointment types,
  clinic booking settings, professionals' booking profile, weekly schedules, any absence;
- professionals (doctor, nurse, physiotherapist): read their own agenda and schedule,
  and add or remove their own absences;
- patients: read active specialties, active appointment types and the clinic settings
  they need to book (slots come from availability.py).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clinical_access import staff_profile
from app.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    Clinic,
    ClinicBookingSettings,
    Patient,
    ScheduleAbsence,
    ScheduleRule,
    ScheduleRuleType,
    Specialty,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.scheduling.availability import MAX_RANGE_DAYS, local_day_bounds
from app.modules.scheduling.booking import CLINICAL_ROLES
from app.modules.scheduling.schemas import (
    AbsenceIn,
    AppointmentTypeCreate,
    AppointmentTypeUpdate,
    BookingSettingsUpdate,
    ProfessionalUpdate,
    ScheduleRuleIn,
    SpecialtyCreate,
    SpecialtyUpdate,
)

ONLY_SCHEDULERS = "Só a administração da clínica gere a configuração das marcações."
NOT_FOUND = "Não encontrado."
ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def is_scheduler(db: Session, user: User) -> bool:
    if user.role == UserRole.CLINIC_ADMIN:
        return True
    staff = staff_profile(db, user) if user.role == UserRole.STAFF else None
    return staff is not None and staff.staff_role == StaffRole.ADMIN


def require_scheduler(db: Session, user: User) -> None:
    if not is_scheduler(db, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ONLY_SCHEDULERS)


def check_range(day_from: date, day_to: date) -> None:
    if day_to < day_from or (day_to - day_from).days >= MAX_RANGE_DAYS:
        raise _unprocessable(f"Escolhe um intervalo de 1 a {MAX_RANGE_DAYS} dias.")


# --- specialties ------------------------------------------------------------------------------


def list_specialties(db: Session, user: User) -> list[Specialty]:
    query = db.query(Specialty).filter(Specialty.clinic_id == user.clinic_id)
    if not is_scheduler(db, user):
        query = query.filter(Specialty.active.is_(True))
    return query.order_by(Specialty.name).all()


def _specialty(db: Session, specialty_id: uuid.UUID, clinic_id: uuid.UUID | str | None) -> Specialty:
    specialty = db.query(Specialty).filter(Specialty.id == specialty_id, Specialty.clinic_id == clinic_id).first()
    if specialty is None:
        raise _not_found()
    return specialty


def _unique_name(db: Session, model: type[Specialty] | type[AppointmentType], clinic_id: object, name: str, exclude: uuid.UUID | None) -> None:
    query = db.query(model.id).filter(model.clinic_id == clinic_id, func.lower(model.name) == name.lower())
    if exclude is not None:
        query = query.filter(model.id != exclude)
    if query.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um registo com esse nome.")


def create_specialty(db: Session, payload: SpecialtyCreate, user: User) -> Specialty:
    require_scheduler(db, user)
    _unique_name(db, Specialty, user.clinic_id, payload.name, None)
    specialty = Specialty(clinic_id=user.clinic_id, name=payload.name)
    db.add(specialty)
    db.commit()
    db.refresh(specialty)
    return specialty


def update_specialty(db: Session, specialty_id: uuid.UUID, payload: SpecialtyUpdate, user: User) -> Specialty:
    require_scheduler(db, user)
    specialty = _specialty(db, specialty_id, user.clinic_id)
    if payload.name is not None:
        _unique_name(db, Specialty, user.clinic_id, payload.name, specialty.id)
        specialty.name = payload.name
    if payload.active is not None:
        specialty.active = payload.active
    db.commit()
    db.refresh(specialty)
    return specialty


# --- appointment types ------------------------------------------------------------------------


def list_types(db: Session, user: User) -> list[AppointmentType]:
    query = db.query(AppointmentType).filter(AppointmentType.clinic_id == user.clinic_id)
    if not is_scheduler(db, user):
        query = query.join(Specialty, Specialty.id == AppointmentType.specialty_id).filter(
            AppointmentType.active.is_(True), Specialty.active.is_(True)
        )
    return query.order_by(AppointmentType.name).all()


def get_type(db: Session, type_id: uuid.UUID, clinic_id: uuid.UUID | str | None, *, active_only: bool) -> AppointmentType:
    query = db.query(AppointmentType).filter(AppointmentType.id == type_id, AppointmentType.clinic_id == clinic_id)
    if active_only:
        query = query.filter(AppointmentType.active.is_(True))
    appointment_type = query.first()
    if appointment_type is None:
        raise _not_found()
    return appointment_type


def create_type(db: Session, payload: AppointmentTypeCreate, user: User) -> AppointmentType:
    require_scheduler(db, user)
    _specialty(db, payload.specialty_id, user.clinic_id)
    _unique_name(db, AppointmentType, user.clinic_id, payload.name, None)
    appointment_type = AppointmentType(clinic_id=user.clinic_id, **payload.model_dump())
    db.add(appointment_type)
    db.commit()
    db.refresh(appointment_type)
    return appointment_type


def update_type(db: Session, type_id: uuid.UUID, payload: AppointmentTypeUpdate, user: User) -> AppointmentType:
    require_scheduler(db, user)
    appointment_type = get_type(db, type_id, user.clinic_id, active_only=False)
    changes = payload.model_dump(exclude_unset=True)
    for required in ("name", "duration_minutes", "specialty_id", "booking_mode", "active"):
        if required in changes and changes[required] is None:
            raise _unprocessable("Campo obrigatório.")
    if "specialty_id" in changes:
        _specialty(db, changes["specialty_id"], user.clinic_id)
    if "name" in changes:
        _unique_name(db, AppointmentType, user.clinic_id, changes["name"], appointment_type.id)
    for field, value in changes.items():
        setattr(appointment_type, field, value)
    db.commit()
    db.refresh(appointment_type)
    return appointment_type


# --- clinic settings --------------------------------------------------------------------------


def get_settings(db: Session, clinic_id: uuid.UUID | str | None) -> ClinicBookingSettings:
    """The clinic's row, or the defaults (not persisted) when it never changed them."""
    settings = db.get(ClinicBookingSettings, clinic_id)
    if settings is not None:
        return settings
    return ClinicBookingSettings(
        clinic_id=clinic_id,
        cancellation_deadline_hours=ClinicBookingSettings.DEFAULT_CANCELLATION_DEADLINE_HOURS,
        waitlist_offer_minutes=ClinicBookingSettings.DEFAULT_WAITLIST_OFFER_MINUTES,
        reminder_hours_before=ClinicBookingSettings.DEFAULT_REMINDER_HOURS_BEFORE,
        booking_horizon_days=ClinicBookingSettings.DEFAULT_BOOKING_HORIZON_DAYS,
    )


def clinic_contact(db: Session, clinic_id: uuid.UUID | str | None) -> tuple[str | None, str | None]:
    """(phone, address) of the clinic."""
    clinic = db.get(Clinic, clinic_id)
    return (clinic.phone, clinic.address) if clinic is not None else (None, None)


def update_settings(db: Session, payload: BookingSettingsUpdate, user: User) -> ClinicBookingSettings:
    require_scheduler(db, user)
    settings = db.get(ClinicBookingSettings, user.clinic_id)
    if settings is None:
        settings = ClinicBookingSettings(clinic_id=user.clinic_id)
        db.add(settings)
    for field, value in payload.model_dump().items():
        setattr(settings, field, value)
    settings.updated_by_user_id = user.id
    db.commit()
    db.refresh(settings)
    return settings


# --- professionals and their weekly schedule ----------------------------------------------------


def professional(db: Session, staff_id: uuid.UUID, clinic_id: uuid.UUID | str | None) -> Staff:
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.clinic_id == clinic_id).first()
    if staff is None or staff.staff_role not in CLINICAL_ROLES:
        raise _not_found()
    return staff


def list_professionals(db: Session, user: User) -> list[tuple[Staff, str]]:
    require_scheduler(db, user)
    rows = (
        db.query(Staff, User.full_name)
        .join(User, Staff.user_id == User.id)
        .filter(Staff.clinic_id == user.clinic_id, Staff.staff_role.in_(CLINICAL_ROLES), User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    return [(staff, name) for staff, name in rows]


def update_professional(db: Session, staff_id: uuid.UUID, payload: ProfessionalUpdate, user: User) -> Staff:
    require_scheduler(db, user)
    staff = professional(db, staff_id, user.clinic_id)
    changes = payload.model_dump(exclude_unset=True)
    if "specialty_id" in changes:
        if changes["specialty_id"] is None:
            staff.specialty_id = None
        else:
            specialty = _specialty(db, changes["specialty_id"], user.clinic_id)
            staff.specialty_id = specialty.id
            staff.specialty = specialty.name  # keep the staff list's label in step
    if changes.get("accepts_new_patients") is not None:
        staff.accepts_new_patients = changes["accepts_new_patients"]
    db.commit()
    db.refresh(staff)
    return staff


def _may_see_agenda(db: Session, user: User, staff: Staff) -> bool:
    return is_scheduler(db, user) or (user.role == UserRole.STAFF and staff.user_id == user.id)


def agenda_professional(db: Session, staff_id: uuid.UUID | None, user: User) -> Staff:
    """The professional whose agenda is requested: oneself by default, anyone for schedulers."""
    if staff_id is None:
        own = staff_profile(db, user) if user.role == UserRole.STAFF else None
        if own is None or own.staff_role not in CLINICAL_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem agenda própria.")
        return own
    staff = professional(db, staff_id, user.clinic_id)
    if not _may_see_agenda(db, user, staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso a esta agenda.")
    return staff


def rules_of(db: Session, staff: Staff) -> list[tuple[ScheduleRule, list[uuid.UUID]]]:
    rules = (
        db.query(ScheduleRule)
        .filter(ScheduleRule.staff_id == staff.id, ScheduleRule.clinic_id == staff.clinic_id)
        .order_by(ScheduleRule.weekday, ScheduleRule.start_time)
        .all()
    )
    types: dict[uuid.UUID, list[uuid.UUID]] = {rule.id: [] for rule in rules}
    if rules:
        for link in db.query(ScheduleRuleType).filter(ScheduleRuleType.rule_id.in_(list(types))):
            types[link.rule_id].append(link.appointment_type_id)
    return [(rule, sorted(types[rule.id], key=str)) for rule in rules]


def _overlap(a: ScheduleRuleIn, b: ScheduleRuleIn) -> bool:
    if a.weekday != b.weekday or not (a.start_time < b.end_time and b.start_time < a.end_time):
        return False
    a_from, a_to = a.valid_from or date.min, a.valid_until or date.max
    b_from, b_to = b.valid_from or date.min, b.valid_until or date.max
    return a_from <= b_to and b_from <= a_to


def replace_schedule(db: Session, staff_id: uuid.UUID, rules: list[ScheduleRuleIn], user: User) -> Staff:
    """Replace a professional's whole weekly schedule (existing appointments are untouched)."""
    require_scheduler(db, user)
    staff = professional(db, staff_id, user.clinic_id)
    for index, rule in enumerate(rules):
        for other in rules[index + 1 :]:
            if _overlap(rule, other):
                raise _unprocessable("Há blocos sobrepostos no mesmo dia da semana.")
    type_ids = {type_id for rule in rules for type_id in rule.appointment_type_ids}
    if type_ids:
        if staff.specialty_id is None:
            raise _unprocessable("Define primeiro a especialidade deste profissional.")
        found = (
            db.query(AppointmentType)
            .filter(AppointmentType.id.in_(type_ids), AppointmentType.clinic_id == user.clinic_id)
            .all()
        )
        if len(found) != len(type_ids):
            raise _not_found()
        if any(appointment_type.specialty_id != staff.specialty_id for appointment_type in found):
            raise _unprocessable("Só podes escolher tipos de consulta da especialidade do profissional.")
    # Serialise concurrent edits of the same schedule.
    db.query(Staff).filter(Staff.id == staff.id).with_for_update().one()
    for existing in db.query(ScheduleRule).filter(
        ScheduleRule.staff_id == staff.id, ScheduleRule.clinic_id == staff.clinic_id
    ):
        db.delete(existing)
    db.flush()
    for rule in rules:
        row = ScheduleRule(
            clinic_id=staff.clinic_id,
            staff_id=staff.id,
            weekday=rule.weekday,
            start_time=rule.start_time,
            end_time=rule.end_time,
            valid_from=rule.valid_from,
            valid_until=rule.valid_until,
        )
        db.add(row)
        db.flush()
        for type_id in dict.fromkeys(rule.appointment_type_ids):
            db.add(ScheduleRuleType(rule_id=row.id, appointment_type_id=type_id, clinic_id=staff.clinic_id))
    db.commit()
    return staff


# --- absences -------------------------------------------------------------------------------------


def conflicting_appointments(db: Session, staff: Staff, starts_at: datetime, ends_at: datetime) -> int:
    return (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.staff_id == staff.id,
            Appointment.clinic_id == staff.clinic_id,
            Appointment.status.in_(ACTIVE),
            Appointment.scheduled_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        .scalar()
        or 0
    )


def add_absence(db: Session, staff_id: uuid.UUID | None, payload: AbsenceIn, user: User) -> tuple[ScheduleAbsence, int]:
    staff = agenda_professional(db, staff_id, user)
    if payload.ends_at - payload.starts_at > timedelta(days=366):
        raise _unprocessable("Uma ausência não pode durar mais de um ano.")
    absence = ScheduleAbsence(
        clinic_id=staff.clinic_id,
        staff_id=staff.id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        kind=payload.kind,
        created_by_user_id=user.id,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return absence, conflicting_appointments(db, staff, absence.starts_at, absence.ends_at)


def delete_absence(db: Session, absence_id: uuid.UUID, user: User) -> ScheduleAbsence:
    absence = (
        db.query(ScheduleAbsence)
        .filter(ScheduleAbsence.id == absence_id, ScheduleAbsence.clinic_id == user.clinic_id)
        .first()
    )
    if absence is None:
        raise _not_found()
    agenda_professional(db, absence.staff_id, user)
    db.delete(absence)
    db.commit()
    return absence


def absences_between(db: Session, staff: Staff, day_from: date, day_to: date) -> list[ScheduleAbsence]:
    start, end = local_day_bounds(day_from, day_to)
    return (
        db.query(ScheduleAbsence)
        .filter(
            ScheduleAbsence.staff_id == staff.id,
            ScheduleAbsence.clinic_id == staff.clinic_id,
            ScheduleAbsence.starts_at < end,
            ScheduleAbsence.ends_at > start,
        )
        .order_by(ScheduleAbsence.starts_at)
        .all()
    )


def agenda_appointments(db: Session, staff: Staff, day_from: date, day_to: date) -> list[tuple[Appointment, str, str]]:
    start, end = local_day_bounds(day_from, day_to)
    rows = (
        db.query(Appointment, User.full_name, AppointmentType.name)
        .join(Patient, Patient.id == Appointment.patient_id)
        .join(User, User.id == Patient.user_id)
        .outerjoin(AppointmentType, AppointmentType.id == Appointment.appointment_type_id)
        .filter(
            Appointment.staff_id == staff.id,
            Appointment.clinic_id == staff.clinic_id,
            Appointment.scheduled_at < end,
            Appointment.ends_at > start,
        )
        .order_by(Appointment.scheduled_at)
        .all()
    )
    return [(appointment, name, type_name or "Consulta") for appointment, name, type_name in rows]


def now_utc() -> datetime:
    return datetime.now(UTC)
