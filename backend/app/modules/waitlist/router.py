"""The patient's waiting list (step 6): join or leave it for one of their appointments,
and accept or decline the earlier slots offered (see app/modules/scheduling/waitlist.py)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import require_roles
from app.models import AuditAction, AuditResult, User, UserRole, WaitlistEntry
from app.modules.appointments.schemas import AppointmentPatientView
from app.modules.appointments.views import patient_views
from app.modules.scheduling import waitlist
from app.modules.scheduling.audit import audit_auto_assignment, audit_released_assignment
from app.modules.waitlist.schemas import WaitlistEntryOut, WaitlistJoin, WaitlistOfferOut

router = APIRouter()
_patient_only = require_roles(UserRole.PATIENT)


def _audit(request: Request, user: User, action: AuditAction, resource_type: str, resource_id: uuid.UUID, **ids: object) -> None:
    # Identifiers only.
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={key: str(value) for key, value in ids.items()} or None,
    )


def _entry_out(entry: WaitlistEntry, offers: list[WaitlistOfferOut] | None = None) -> WaitlistEntryOut:
    return WaitlistEntryOut(
        id=entry.id,
        appointment_id=entry.appointment_id,
        scope=entry.scope,
        status=entry.status,
        created_at=entry.created_at,
        offers=offers or [],
    )


@router.get("", response_model=list[WaitlistEntryOut])
def list_mine(db: Session = Depends(get_db), user: User = Depends(_patient_only)) -> list[WaitlistEntryOut]:
    """The patient's active entries with their open offers."""
    return [
        _entry_out(
            entry,
            [
                WaitlistOfferOut(id=offer.id, starts_at=offer.starts_at, ends_at=offer.ends_at, staff_name=name, expires_at=offer.expires_at)
                for offer, name in offers
            ],
        )
        for entry, offers in waitlist.list_for_patient(db, user)
    ]


@router.post("", response_model=WaitlistEntryOut, status_code=201)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def join(payload: WaitlistJoin, request: Request, db: Session = Depends(get_db), user: User = Depends(_patient_only)) -> WaitlistEntryOut:
    """Join the waiting list for one of the patient's appointments (409 if already on it, or
    past the clinic's deadline; 422 for types booked only by request)."""
    entry = waitlist.join(db, user, payload.appointment_id, payload.scope)
    _audit(request, user, AuditAction.WAITLIST_JOINED, "waitlist_entry", entry.id, appointment_id=entry.appointment_id, operation=entry.scope.value)
    return _entry_out(entry)


@router.post("/{entry_id}/leave", response_model=WaitlistEntryOut)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def leave(entry_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(_patient_only)) -> WaitlistEntryOut:
    entry = waitlist.leave(db, user, entry_id)
    _audit(request, user, AuditAction.WAITLIST_LEFT, "waitlist_entry", entry.id, appointment_id=entry.appointment_id)
    return _entry_out(entry)


@router.post("/offers/{offer_id}/accept", response_model=AppointmentPatientView, status_code=201)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def accept_offer(
    offer_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(_patient_only)
) -> AppointmentPatientView:
    """Take the earlier slot: the new appointment is booked and the old one cancelled together
    (409, nothing changed, if the slot was taken or the offer expired). Returns the new one."""
    new, old, created, ended = waitlist.accept_offer(db, user, offer_id)
    _audit(request, user, AuditAction.WAITLIST_OFFER_ACCEPTED, "waitlist_offer", offer_id, appointment_id=new.id)
    _audit(request, user, AuditAction.APPOINTMENT_RESCHEDULED, "appointment", old.id, new_appointment_id=new.id, via="waitlist")
    _audit(request, user, AuditAction.APPOINTMENT_CREATED, "appointment", new.id, patient_id=new.patient_id, staff_id=new.staff_id, via="waitlist")
    audit_released_assignment(request, user, ended, old.id, via="appointment_moved")
    audit_auto_assignment(request, user, created, new.id)
    return patient_views(db, [new])[0]


@router.post("/offers/{offer_id}/decline", status_code=204)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def decline_offer(offer_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(_patient_only)) -> None:
    waitlist.decline_offer(db, user, offer_id)
    _audit(request, user, AuditAction.WAITLIST_OFFER_DECLINED, "waitlist_offer", offer_id)
