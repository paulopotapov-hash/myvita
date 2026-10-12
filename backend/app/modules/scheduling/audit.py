"""Audit helpers for scheduling: identifiers only (never names, reasons or times)."""

from fastapi import Request

from app.core.audit import record_audit_event
from app.core.client_ip import get_client_ip
from app.models import AuditAction, AuditResult, User
from app.modules.scheduling.booking import AutoAssignment


def audit_auto_assignment(request: Request, actor: User, assignment: AutoAssignment | None, appointment_id: object) -> None:
    if assignment is None:
        return
    record_audit_event(
        action=AuditAction.CARE_ASSIGNMENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=actor.clinic_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        resource_type="care_assignment",
        resource_id=assignment.assignment_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "patient_id": assignment.patient_id,
            "staff_id": assignment.staff_id,
            "appointment_id": appointment_id,
            "via": "appointment",
        },
    )


def audit_released_assignment(
    request: Request, actor: User, assignment: AutoAssignment | None, appointment_id: object, *, via: str
) -> None:
    """The automatic link ended with its appointment (`via`: "appointment_cancelled" or
    "appointment_moved")."""
    if assignment is None:
        return
    record_audit_event(
        action=AuditAction.CARE_ASSIGNMENT_ENDED,
        result=AuditResult.SUCCESS,
        clinic_id=actor.clinic_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        resource_type="care_assignment",
        resource_id=assignment.assignment_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "patient_id": assignment.patient_id,
            "staff_id": assignment.staff_id,
            "appointment_id": appointment_id,
            "via": via,
        },
    )


def audit_scheduling(
    request: Request, actor: User, action: AuditAction, resource_type: str, resource_id: object, **ids: object
) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=actor.clinic_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        resource_type=resource_type,
        resource_id=resource_id,  # type: ignore[arg-type]
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata=dict(ids) or None,
    )
