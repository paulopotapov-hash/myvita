"""
Covers the appointment-booking feature added in v0.2, including the
cross-clinic IDOR attack scenario found and blocked during manual testing:
a clinic admin must not be able to book an appointment using another
clinic's patient_id or staff_id.

Since v0.2.1, every state-changing authenticated request also requires a
valid CSRF token (see tests/test_csrf.py for the dedicated CSRF test
suite). These tests switch between several logged-in identities on the
SAME TestClient instance, so we must save/restore BOTH the session cookie
AND the matching CSRF cookie for each identity — the CSRF token is bound
to a specific user's session, not shared across identities.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import Appointment, AuditAction, AuditLog, Notification, User
from app.modules.appointments.schemas import AppointmentCreateRequest
from app.modules.appointments.service import create_appointment
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.test_session_factory = TestSessionLocal
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _capture_identity(response) -> dict:
    """Grabs both the session cookie and its matching CSRF cookie from a
    login/registration response, so we can restore this exact identity
    later even after the client has moved on to a different session."""
    return {
        "session": response.cookies.get(settings.COOKIE_NAME),
        "csrf": response.cookies.get(settings.CSRF_COOKIE_NAME),
    }


def _use_identity(client, identity: dict) -> dict:
    """Switches the shared TestClient to the given identity's session, and
    returns the header dict to pass on state-changing requests."""
    client.cookies.set(settings.COOKIE_NAME, identity["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, identity["csrf"])
    return {settings.CSRF_HEADER_NAME: identity["csrf"]}


def _new_clinic_with_staff_and_patient(client, suffix: str):
    r = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Clínica {suffix}",
            "admin_full_name": f"Admin {suffix}",
            "admin_email": f"admin{suffix}@x.pt",
            "admin_password": "SenhaForte123!",
        },
    )
    admin = _capture_identity(r)
    clinic_id = r.json()["id"]

    admin_headers = _use_identity(client, admin)
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": f"Dr. {suffix}",
            "email": f"doctor{suffix}@x.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
        headers=admin_headers,
    )
    staff_id = r.json()["id"]

    r = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Paciente {suffix}",
            "email": f"patient{suffix}@x.pt",
            "password": "SenhaForte123!",
        },
    )
    patient_id = r.json()["id"]
    patient = _capture_identity(r)

    return {
        "clinic_id": clinic_id,
        "admin": admin,
        "staff_id": staff_id,
        "patient_id": patient_id,
        "patient": patient,
    }


def test_staff_can_book_appointment_for_their_clinic(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["admin"])

    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "scheduled"

    _use_identity(client, a["patient"])
    notifications = client.get("/api/v1/notifications?page=1&page_size=20")
    assert notifications.status_code == 200
    assert notifications.headers["X-Total-Count"] == "1"
    assert notifications.json()[0]["title"] == "Consulta criada"


def test_appointment_notifications_skip_noops_and_cover_updates_and_cancellation(client):
    tenant = _new_clinic_with_staff_and_patient(client, "event-notifications")
    admin_headers = _use_identity(client, tenant["admin"])
    created = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": tenant["patient_id"],
            "staff_id": tenant["staff_id"],
            "scheduled_at": "2026-10-03T10:00:00Z",
        },
        headers=admin_headers,
    )
    appointment_id = created.json()["id"]
    client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"reason": "Novo detalhe", "duration_minutes": 45},
        headers=admin_headers,
    )
    _use_identity(client, tenant["patient"])
    assert client.get("/api/v1/notifications").headers["X-Total-Count"] == "1"

    _use_identity(client, tenant["admin"])
    changed = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"scheduled_at": "2026-10-03T11:00:00Z"},
        headers=admin_headers,
    )
    assert changed.status_code == 200
    cancelled = client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=admin_headers)
    assert cancelled.status_code == 200
    _use_identity(client, tenant["patient"])
    notifications = client.get("/api/v1/notifications")
    assert notifications.headers["X-Total-Count"] == "3"
    assert {item["title"] for item in notifications.json()} == {
        "Consulta criada",
        "Consulta atualizada",
        "Consulta cancelada",
    }


def test_notification_failure_rolls_back_appointment(client, monkeypatch):
    tenant = _new_clinic_with_staff_and_patient(client, "atomic")
    headers = _use_identity(client, tenant["admin"])

    def fail_notification(*_args, **_kwargs):
        raise RuntimeError("synthetic notification failure")

    monkeypatch.setattr("app.modules.appointments.service._add_patient_notification", fail_notification)
    with pytest.raises(RuntimeError, match="synthetic notification failure"):
        client.post(
            "/api/v1/appointments",
            json={
                "patient_id": tenant["patient_id"],
                "staff_id": tenant["staff_id"],
                "scheduled_at": "2026-10-01T12:00:00Z",
            },
            headers=headers,
        )

    db = client.test_session_factory()
    try:
        assert db.query(Appointment).count() == 0
    finally:
        db.close()


def test_notification_failure_rolls_back_update_and_cancel(client, monkeypatch):
    tenant = _new_clinic_with_staff_and_patient(client, "atomic-mutations")
    headers = _use_identity(client, tenant["admin"])
    created = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": tenant["patient_id"],
            "staff_id": tenant["staff_id"],
            "scheduled_at": "2026-10-01T13:00:00Z",
        },
        headers=headers,
    )
    appointment_id = created.json()["id"]

    def fail_notification(*_args, **_kwargs):
        raise RuntimeError("synthetic notification failure")

    monkeypatch.setattr("app.modules.appointments.service._add_patient_notification", fail_notification)
    with pytest.raises(RuntimeError, match="synthetic notification failure"):
        client.patch(
            f"/api/v1/appointments/{appointment_id}",
            json={"scheduled_at": "2026-10-01T13:30:00Z"},
            headers=headers,
        )
    with pytest.raises(RuntimeError, match="synthetic notification failure"):
        client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers)

    db = client.test_session_factory()
    try:
        appointment = db.get(Appointment, appointment_id)
        assert appointment is not None
        assert appointment.duration_minutes == 30
        assert appointment.status.value == "scheduled"
    finally:
        db.close()


def test_appointment_list_is_paginated_after_tenant_scope(client):
    a = _new_clinic_with_staff_and_patient(client, "paged")
    headers = _use_identity(client, a["admin"])
    for hour in (9, 10, 11):
        response = client.post(
            "/api/v1/appointments",
            json={
                "patient_id": a["patient_id"],
                "staff_id": a["staff_id"],
                "scheduled_at": f"2026-10-02T{hour:02d}:00:00Z",
            },
            headers=headers,
        )
        assert response.status_code == 201

    page = client.get("/api/v1/appointments?page=2&page_size=2")
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "3"
    assert len(page.json()) == 1


def test_concurrent_overlapping_bookings_allow_only_one(client):
    tenant = _new_clinic_with_staff_and_patient(client, "concurrent")
    barrier = Barrier(2)
    payload = AppointmentCreateRequest(
        patient_id=tenant["patient_id"],
        staff_id=tenant["staff_id"],
        scheduled_at="2026-10-08T10:00:00Z",
        duration_minutes=30,
    )

    def book() -> int:
        db = client.test_session_factory()
        try:
            barrier.wait()
            create_appointment(db, tenant["clinic_id"], payload)
            return 201
        except HTTPException as exc:
            db.rollback()
            return exc.status_code
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(book) for _ in range(2)]
        statuses = sorted(future.result() for future in futures)

    assert statuses == [201, 409]


def test_patient_sees_only_their_own_appointment(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["admin"])
    client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
        },
        headers=headers,
    )

    _use_identity(client, a["patient"])
    r = client.get("/api/v1/appointments")  # GET — no CSRF header needed
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["patient_id"] == a["patient_id"]


def test_patient_cannot_create_appointments_directly(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["patient"])

    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 403


def test_notification_count_read_and_read_all_are_user_and_clinic_scoped(client):
    first = _new_clinic_with_staff_and_patient(client, "notification-scope-a")
    second = _new_clinic_with_staff_and_patient(client, "notification-scope-b")
    db = client.test_session_factory()
    try:
        first_user = db.query(User).filter(User.email == "patientnotification-scope-a@x.pt").one()
        same_clinic_admin = db.query(User).filter(User.email == "adminnotification-scope-a@x.pt").one()
        mine = Notification(
            clinic_id=first["clinic_id"], user_id=first_user.id, title="Mine", message="Appointment"
        )
        already_read = Notification(
            clinic_id=first["clinic_id"],
            user_id=first_user.id,
            title="Read",
            message="Appointment",
            is_read=True,
            read_at=datetime.now(UTC),
        )
        other_user = Notification(
            clinic_id=first["clinic_id"],
            user_id=same_clinic_admin.id,
            title="Other user",
            message="Appointment",
        )
        other_clinic = Notification(
            clinic_id=second["clinic_id"],
            user_id=first_user.id,
            title="Other clinic",
            message="Appointment",
        )
        db.add_all([mine, already_read, other_user, other_clinic])
        db.commit()
        mine_id = mine.id
        read_id = already_read.id
        existing_read_at = already_read.read_at
        other_user_id = other_user.id
        other_clinic_id = other_clinic.id
    finally:
        db.close()

    client.cookies.clear()
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/notifications/read-all").status_code == 401
    admin_headers = _use_identity(client, first["admin"])
    assert [item["title"] for item in client.get("/api/v1/notifications").json()] == ["Other user"]
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}
    headers = _use_identity(client, first["patient"])
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}
    assert {item["title"] for item in client.get("/api/v1/notifications").json()} == {"Mine", "Read"}
    assert client.post(f"/api/v1/notifications/{other_user_id}/read", headers=headers).status_code == 404
    assert client.post(f"/api/v1/notifications/{other_clinic_id}/read", headers=headers).status_code == 404

    read = client.post(f"/api/v1/notifications/{mine_id}/read", headers=headers)
    assert read.status_code == 200
    first_read_at = read.json()["read_at"]
    read_again = client.post(f"/api/v1/notifications/{mine_id}/read", headers=headers)
    assert read_again.json()["read_at"] == first_read_at
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}

    db = client.test_session_factory()
    try:
        db.query(Notification).filter(Notification.id == mine_id).update(
            {Notification.is_read: False, Notification.read_at: None}
        )
        db.commit()
    finally:
        db.close()
    result = client.post("/api/v1/notifications/read-all", headers=headers)
    assert result.status_code == 200
    assert result.json() == {"updated_count": 1}
    assert client.post("/api/v1/notifications/read-all", headers=headers).json() == {"updated_count": 0}
    db = client.test_session_factory()
    try:
        assert db.get(Notification, mine_id).read_at is not None
        assert db.get(Notification, read_id).read_at == existing_read_at
        assert db.get(Notification, other_user_id).is_read is False
        assert db.get(Notification, other_clinic_id).is_read is False
        assert db.query(AuditLog).filter(AuditLog.action == AuditAction.NOTIFICATION_READ).count() >= 3
    finally:
        db.close()
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}
    admin_headers = _use_identity(client, first["admin"])
    assert (
        client.post(f"/api/v1/notifications/{other_user_id}/read", headers=admin_headers).status_code == 200
    )


def test_cross_clinic_idor_using_another_clinics_patient_is_blocked(client):
    """
    The core regression test for the bug class found during manual testing:
    clinic B's admin must not be able to book an appointment against
    clinic A's patient, even though both IDs are individually valid.
    """
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, b["admin"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],  # clinic A's patient
            "staff_id": b["staff_id"],  # clinic B's own staff
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 404


def test_cross_clinic_idor_using_another_clinics_staff_is_blocked(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, b["admin"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": b["patient_id"],  # clinic B's own patient
            "staff_id": a["staff_id"],  # clinic A's staff — not theirs to use
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 404


def test_staff_list_only_shows_own_clinic_appointments(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, a["admin"])
    client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
        },
        headers=headers,
    )

    headers = _use_identity(client, b["admin"])
    client.post(
        "/api/v1/appointments",
        json={
            "patient_id": b["patient_id"],
            "staff_id": b["staff_id"],
            "scheduled_at": "2026-10-01T11:00:00Z",
        },
        headers=headers,
    )

    r = client.get("/api/v1/appointments")  # still authenticated as clinic B's admin, GET needs no CSRF
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["clinic_id"] == b["clinic_id"]
