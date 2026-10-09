"""Clinical access is assignment-based (Parent A model, kept at merge time):
clinic admins and administrative staff schedule for any patient of the clinic;
doctors/nurses only see and act on patients on their active care team. These
tests pin that rule on the appointments listing (with pagination) and on the
P2.3 appointment-request triage endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.rate_limit import limiter
from app.models import AuditAction, AuditLog, AuditResult
from tests.phase1_world import Actor, World, fresh_patient

REQUESTS = "/api/v1/appointment-requests"


def _slot(days: int, hour: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _new_request(patient: Actor, days: int) -> str:
    limiter.reset()
    created = patient.post(REQUESTS, json={"preferred_start": _slot(days), "reason": "ACCESS-RULE-MARKER"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _accept_body(staff_id: str, days: int) -> dict:
    return {"staff_id": staff_id, "scheduled_at": _slot(days, 11), "duration_minutes": 30}


# --- appointments listing -------------------------------------------------------


def test_clinicians_list_only_assigned_patients_appointments_and_total_matches(world: World):
    tenant = world.a
    unassigned = fresh_patient(world, tenant, "unassigned-appt")
    # Administrative staff books the unassigned patient with the doctor (allowed: scheduler role).
    booked = tenant.staff_admin.post(
        "/api/v1/appointments",
        json={
            "patient_id": unassigned.patient_id,
            "staff_id": tenant.doctor.staff_id,
            "scheduled_at": _slot(50),
            "duration_minutes": 30,
        },
    )
    assert booked.status_code == 201, booked.text

    seen_by_doctor = tenant.doctor.get("/api/v1/appointments?page_size=100")
    assert seen_by_doctor.status_code == 200
    doctor_patients = {row["patient_id"] for row in seen_by_doctor.json()}
    assert unassigned.patient_id not in doctor_patients
    assert {p.patient_id for p in tenant.patients.values()} <= doctor_patients
    assert seen_by_doctor.headers["X-Total-Count"] == str(len(seen_by_doctor.json()))

    for scheduler in (tenant.admin, tenant.staff_admin):
        seen = scheduler.get("/api/v1/appointments?page_size=100")
        assert seen.status_code == 200
        assert unassigned.patient_id in {row["patient_id"] for row in seen.json()}
        assert int(seen.headers["X-Total-Count"]) > len(doctor_patients)

    # Pagination is applied after the visibility filter.
    page = tenant.doctor.get("/api/v1/appointments?page=1&page_size=1")
    assert page.status_code == 200 and len(page.json()) == 1
    assert page.headers["X-Total-Count"] == seen_by_doctor.headers["X-Total-Count"]


# --- appointment requests ---------------------------------------------------------


def test_schedulers_see_and_decide_requests_of_unassigned_patients(world: World):
    tenant = world.a
    patient = fresh_patient(world, tenant, "unassigned-req")
    request_id = _new_request(patient, 41)

    for scheduler in (tenant.admin, tenant.staff_admin):
        listed = scheduler.get(f"{REQUESTS}?page_size=100")
        assert listed.status_code == 200
        assert request_id in {row["id"] for row in listed.json()}

    accepted = tenant.staff_admin.post(f"{REQUESTS}/{request_id}/accept", json=_accept_body(tenant.doctor.staff_id, 41))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"


def test_clinicians_cannot_see_or_decide_requests_of_patients_outside_their_care_team(world: World):
    tenant = world.a
    patient = fresh_patient(world, tenant, "foreign-req")
    request_id = _new_request(patient, 42)

    for clinician in (tenant.doctor, tenant.nurse):
        listed = clinician.get(f"{REQUESTS}?page_size=100")
        assert listed.status_code == 200
        assert request_id not in {row["id"] for row in listed.json()}
        limiter.reset()
        assert clinician.post(f"{REQUESTS}/{request_id}/reject").status_code == 403
        limiter.reset()
        denied = clinician.post(f"{REQUESTS}/{request_id}/accept", json=_accept_body(clinician.staff_id, 42))
        assert denied.status_code == 403

    # The request is untouched and the denial is audited under the actor.
    still_pending = tenant.admin.get(f"{REQUESTS}?page_size=100")
    assert next(row for row in still_pending.json() if row["id"] == request_id)["status"] == "pending"
    with world.db() as db:
        denials = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == AuditAction.PERMISSION_DENIED,
                AuditLog.resource_type == "appointment_request",
                AuditLog.resource_id == uuid.UUID(request_id),
            )
            .all()
        )
    assert len(denials) >= 2 and all(row.result == AuditResult.DENIED for row in denials)
    assert {str(row.actor_user_id) for row in denials} == {tenant.doctor.user_id, tenant.nurse.user_id}


def test_clinicians_see_and_decide_requests_of_their_own_patients(world: World):
    tenant = world.a
    patient = tenant.patients["a2"]  # on the doctor's and nurse's care team (phase1_world)
    request_id = _new_request(patient, 43)

    listed = tenant.nurse.get(f"{REQUESTS}?page_size=100")
    assert request_id in {row["id"] for row in listed.json()}
    limiter.reset()
    rejected = tenant.doctor.post(f"{REQUESTS}/{request_id}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"


def test_requests_from_another_clinic_stay_invisible_to_schedulers(world: World):
    patient_b = fresh_patient(world, world.b, "cross-req")
    request_id = _new_request(patient_b, 44)
    limiter.reset()
    assert world.a.admin.post(f"{REQUESTS}/{request_id}/reject").status_code == 404
    limiter.reset()
    assert world.a.staff_admin.post(f"{REQUESTS}/{request_id}/accept", json=_accept_body(world.a.doctor.staff_id, 44)).status_code == 404
    assert request_id not in {row["id"] for row in world.a.admin.get(f"{REQUESTS}?page_size=100").json()}
