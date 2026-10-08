"""
P2.3 — patient appointment requests on the committed two-clinic dataset
(tests/phase1_world.py): lifecycle, authorization, tenant isolation,
concurrency, notifications and audit.
"""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.rate_limit import limiter
from app.models import (
    Appointment,
    AppointmentRequest,
    AppointmentRequestStatus,
    AuditAction,
    AuditLog,
    Notification,
    User,
)
from tests.phase1_world import Actor, World, fresh_patient

BASE = "/api/v1/appointment-requests"
SECRET_REASON = "P23-CLINICAL-REASON-MARKER"


def _slot(days: int, hour: int = 10) -> str:
    start = (datetime.now(UTC) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return start.isoformat()


def _request(patient: Actor, days: int = 40, reason: str | None = SECRET_REASON, **extra):
    limiter.reset()
    body = {"preferred_start": _slot(days), **extra}
    if reason is not None:
        body["reason"] = reason
    return patient.post(BASE, json=body)


def _accept(actor: Actor, request_id: str, staff_id: str, days: int, hour: int = 10):
    limiter.reset()
    return actor.post(
        f"{BASE}/{request_id}/accept",
        json={"staff_id": staff_id, "scheduled_at": _slot(days, hour), "duration_minutes": 30},
    )


def test_patient_request_accept_lifecycle_creates_one_normal_appointment(world: World):
    patient = fresh_patient(world, world.a, "req-accept")
    created = _request(patient, 41)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending" and body["appointment_id"] is None
    assert body["patient_id"] == patient.patient_id and body["clinic_id"] == world.a.clinic_id
    assert body["reason"] == SECRET_REASON

    mine = patient.get(BASE)
    assert [r["id"] for r in mine.json()] == [body["id"]] and mine.headers["X-Total-Count"] == "1"

    # Scheduling roles see it pending; only clinical staff see the reason.
    for actor, sees_reason in ((world.a.doctor, True), (world.a.nurse, True), (world.a.admin, False), (world.a.staff_admin, False)):
        listed = {r["id"]: r for r in actor.get(f"{BASE}?page_size=100").json()}
        assert body["id"] in listed
        assert (listed[body["id"]]["reason"] == SECRET_REASON) is sees_reason
        assert listed[body["id"]]["patient_name"]

    accepted = _accept(world.a.staff_admin, body["id"], world.a.doctor.staff_id, 41)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted" and accepted.json()["reason"] is None
    appointment_id = accepted.json()["appointment_id"]

    appointment = patient.get(f"/api/v1/appointments/{appointment_id}")
    assert appointment.status_code == 200
    assert appointment.json()["staff_id"] == world.a.doctor.staff_id
    assert appointment.json()["status"] == "scheduled"
    assert appointment.json()["reason"] == SECRET_REASON
    assert patient.get(BASE).json()[0]["status"] == "accepted"

    # Accepted is final.
    assert _accept(world.a.admin, body["id"], world.a.doctor.staff_id, 42).status_code == 409
    assert world.a.admin.post(f"{BASE}/{body['id']}/reject").status_code == 409
    assert patient.post(f"{BASE}/{body['id']}/cancel").status_code == 409
    assert body["id"] not in {r["id"] for r in world.a.admin.get(BASE).json()}
    assert body["id"] in {r["id"] for r in world.a.admin.get(f"{BASE}?status=accepted&page_size=100").json()}


def test_reject_and_cancel_are_final_and_create_no_appointment(world: World):
    patient = fresh_patient(world, world.a, "req-reject")
    rejected_id = _request(patient, 43).json()["id"]
    cancelled_id = _request(patient, 44, reason=None).json()["id"]

    rejected = world.a.doctor.post(f"{BASE}/{rejected_id}/reject")
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert _accept(world.a.admin, rejected_id, world.a.doctor.staff_id, 43).status_code == 409
    assert patient.post(f"{BASE}/{rejected_id}/cancel").status_code == 409

    cancelled = patient.post(f"{BASE}/{cancelled_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert _accept(world.a.admin, cancelled_id, world.a.doctor.staff_id, 44).status_code == 409
    assert world.a.admin.post(f"{BASE}/{cancelled_id}/reject").status_code == 409

    with world.db() as db:
        for request_id in (rejected_id, cancelled_id):
            row = db.get(AppointmentRequest, uuid.UUID(request_id))
            assert row.appointment_id is None
        assert db.scalars(
            select(Appointment).where(Appointment.patient_id == uuid.UUID(patient.patient_id))
        ).all() == []


def test_patient_cannot_choose_patient_clinic_professional_or_status(world: World):
    patient = fresh_patient(world, world.a, "req-smuggle")
    other = world.a.patients["a1"]
    for field, value in (
        ("patient_id", other.patient_id),
        ("clinic_id", world.b.clinic_id),
        ("staff_id", world.a.doctor.staff_id),
        ("status", "accepted"),
        ("appointment_id", str(uuid.uuid4())),
    ):
        assert _request(patient, 45, **{field: value}).status_code == 422, field
    assert _request(patient, -1).status_code == 422  # past date
    limiter.reset()
    assert patient.post(BASE, json={"preferred_start": "2031-01-01T10:00:00"}).status_code == 422  # no timezone
    assert patient.post(BASE, json={"preferred_start": _slot(45), "reason": "x" * 501}).status_code == 422

    request_id = _request(patient, 46).json()["id"]
    # A patient can never review, even their own request.
    assert _accept(patient, request_id, world.a.doctor.staff_id, 46).status_code == 403
    assert patient.post(f"{BASE}/{request_id}/reject").status_code == 403
    # Staff cannot create requests on a patient's behalf through this API.
    assert _request(world.a.doctor, 46).status_code == 403
    assert _request(world.a.admin, 46).status_code == 403


def test_patients_and_clinics_are_isolated(world: World):
    patient = fresh_patient(world, world.a, "req-iso")
    request_id = _request(patient, 47).json()["id"]
    other_patient = world.a.patients["a2"]
    assert request_id not in {r["id"] for r in other_patient.get(BASE).json()}
    assert other_patient.post(f"{BASE}/{request_id}/cancel").status_code == 404
    for actor in world.b.everyone:
        listed = actor.get(f"{BASE}?page_size=100")
        assert listed.status_code == 200
        assert request_id not in {r["id"] for r in listed.json()}
        assert all(r["clinic_id"] == world.b.clinic_id for r in listed.json())
    for actor in (world.b.admin, world.b.doctor, world.b.staff_admin):
        assert _accept(actor, request_id, actor.staff_id or world.b.doctor.staff_id, 47).status_code == 404
        assert actor.post(f"{BASE}/{request_id}/reject").status_code == 404
    # Clinic A staff cannot assign a clinic B professional (existing tenant check).
    assert _accept(world.a.admin, request_id, world.b.doctor.staff_id, 47).status_code == 404
    assert _accept(world.a.admin, str(uuid.uuid4()), world.a.doctor.staff_id, 47).status_code == 404
    for method, path in (("GET", BASE), ("POST", f"{BASE}/{request_id}/accept"), ("POST", f"{BASE}/{request_id}/cancel")):
        assert Actor("anon").call(method, path, json={}).status_code == 401
    with world.db() as db:
        assert db.get(AppointmentRequest, uuid.UUID(request_id)).status == AppointmentRequestStatus.PENDING


def test_overlap_rejection_keeps_the_request_pending(world: World):
    patient = fresh_patient(world, world.a, "req-overlap")
    first = _request(patient, 48).json()["id"]
    second = _request(patient, 48).json()["id"]
    assert _accept(world.a.admin, first, world.a.nurse.staff_id, 48, 15).status_code == 200
    clash = _accept(world.a.admin, second, world.a.nurse.staff_id, 48, 15)
    assert clash.status_code == 409
    with world.db() as db:
        row = db.get(AppointmentRequest, uuid.UUID(second))
        assert row.status == AppointmentRequestStatus.PENDING and row.appointment_id is None
    assert _accept(world.a.admin, second, world.a.nurse.staff_id, 48, 16).status_code == 200


def test_concurrent_acceptance_creates_exactly_one_appointment(world: World):
    patient = fresh_patient(world, world.a, "req-race")
    request_id = _request(patient, 49).json()["id"]
    reviewers = [Actor(f"race-{i}", world.a.admin.email) for i in range(4)]
    for reviewer in reviewers:
        assert reviewer.login().status_code == 200
    limiter.reset()
    barrier = threading.Barrier(len(reviewers))
    statuses: list[int] = []

    def run(actor: Actor, hour: int) -> None:
        barrier.wait()
        response = actor.post(
            f"{BASE}/{request_id}/accept",
            json={"staff_id": world.a.doctor.staff_id, "scheduled_at": _slot(49, hour), "duration_minutes": 30},
        )
        statuses.append(response.status_code)

    threads = [threading.Thread(target=run, args=(actor, 9 + i)) for i, actor in enumerate(reviewers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert statuses.count(200) == 1, statuses
    assert sorted(set(statuses) - {200}) == [409], statuses
    with world.db() as db:
        row = db.get(AppointmentRequest, uuid.UUID(request_id))
        assert row.status == AppointmentRequestStatus.ACCEPTED and row.appointment_id is not None
        appointments = db.scalars(
            select(Appointment).where(Appointment.patient_id == uuid.UUID(patient.patient_id))
        ).all()
        assert [a.id for a in appointments] == [row.appointment_id]


def test_pending_limit(world: World):
    patient = fresh_patient(world, world.a, "req-limit")
    for i in range(5):
        assert _request(patient, 50 + i).status_code == 201
    assert _request(patient, 56).status_code == 409


def test_notifications_and_audit_carry_no_clinical_content(world: World):
    patient = fresh_patient(world, world.a, "req-notify")
    accepted_id = _request(patient, 57).json()["id"]
    rejected_id = _request(patient, 58).json()["id"]
    cancelled_id = _request(patient, 59).json()["id"]
    assert _accept(world.a.admin, accepted_id, world.a.doctor.staff_id, 57).status_code == 200
    assert world.a.admin.post(f"{BASE}/{rejected_id}/reject").status_code == 200
    assert patient.post(f"{BASE}/{cancelled_id}/cancel").status_code == 200

    with world.db() as db:
        def titles(email: str) -> list[str]:
            user = db.scalars(select(User).where(User.email == email)).one()
            return [n.title for n in db.scalars(select(Notification).where(Notification.user_id == user.id)).all()]

        patient_titles = titles(patient.email)
        assert "Pedido de consulta aceite" in patient_titles
        assert "Pedido de consulta recusado" in patient_titles
        # Schedulers (clinic admin, administrative staff) are told about new requests; others in clinic B are not.
        assert titles(world.a.admin.email).count("Novo pedido de consulta") >= 3
        assert "Novo pedido de consulta" in titles(world.a.staff_admin.email)
        assert "Novo pedido de consulta" not in titles(world.b.admin.email)
        for row in db.scalars(select(Notification)).all():
            assert SECRET_REASON not in row.title + row.message

        def audited(action: AuditAction, request_id: str) -> list[AuditLog]:
            return db.scalars(
                select(AuditLog).where(AuditLog.action == action, AuditLog.resource_id == uuid.UUID(request_id))
            ).all()

        assert audited(AuditAction.APPOINTMENT_REQUEST_CREATED, accepted_id)
        accepted = audited(AuditAction.APPOINTMENT_REQUEST_ACCEPTED, accepted_id)
        assert accepted and accepted[0].event_metadata.get("appointment_id")
        assert audited(AuditAction.APPOINTMENT_REQUEST_REJECTED, rejected_id)
        assert audited(AuditAction.APPOINTMENT_REQUEST_CANCELLED, cancelled_id)
        for row in db.scalars(select(AuditLog).where(AuditLog.resource_type == "appointment_request")).all():
            assert SECRET_REASON not in repr(row.event_metadata)
