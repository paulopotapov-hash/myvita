"""End-to-end clinical flows, tenant boundaries, role checks and CSRF."""
# ruff: noqa: F401, F811
from datetime import UTC, date, datetime, timedelta

from tests.test_appointments_integration import (
    _future_iso,
    _new_clinic_with_staff_and_patient,
    _use_identity,
    client,
)


def test_clinical_history_and_cross_tenant_guards(client):
    a = _new_clinic_with_staff_and_patient(client, "ClinicalA")
    b = _new_clinic_with_staff_and_patient(client, "ClinicalB")
    ah = _use_identity(client, a["staff"])
    base = "/api/v1"
    r = client.post(f"{base}/medical-records", json={"patient_id": a["patient_id"], "title": "Consulta", "content": "Observação"}, headers=ah)
    assert r.status_code == 201, r.text
    record_id = r.json()["id"]
    assert client.get(f"{base}/patients/{a['patient_id']}/medical-records").status_code == 200
    assert client.patch(f"{base}/medical-records/{record_id}", json={"content": "Seguimento"}, headers=ah).status_code == 200
    future_date = (date.today() + timedelta(days=30)).isoformat()
    r = client.post(f"{base}/medications", json={"patient_id": a["patient_id"], "name": "Med A", "dose": "1", "frequency": "daily", "start_date": future_date}, headers=ah)
    assert r.status_code == 201, r.text
    medication_id = r.json()["id"]
    assert client.patch(f"{base}/medications/{medication_id}", json={"is_active": False}, headers=ah).json()["is_active"] is False
    r = client.post(f"{base}/consents", json={"patient_id": a["patient_id"], "consent_type": "care", "status": "granted", "version": "1", "effective_at": _future_iso()}, headers=ah)
    assert r.status_code == 201, r.text
    assert len(client.get(f"{base}/patients/{a['patient_id']}/consents").json()) == 1
    bh = _use_identity(client, b["staff"])
    assert client.get(f"{base}/patients/{a['patient_id']}/medical-records").status_code == 404
    assert client.patch(f"{base}/medical-records/{record_id}", json={"content": "x"}, headers=bh).status_code == 404
    assert client.patch(f"{base}/medications/{medication_id}", json={"is_active": True}, headers=bh).status_code == 404
    assert client.post(f"{base}/consents", json={"patient_id": a["patient_id"], "consent_type": "care", "status": "granted", "version": "1", "effective_at": _future_iso()}, headers=bh).status_code == 404
    ph = _use_identity(client, a["patient"])
    assert client.get(f"{base}/patients/{a['patient_id']}/medical-records").status_code == 200
    assert client.post(f"{base}/medical-records", json={"patient_id": a["patient_id"], "title": "X", "content": "X"}, headers=ph).status_code == 403
    assert client.patch(f"{base}/medical-records/{record_id}", json={"content": "X"}, headers=ph).status_code == 403
    assert client.get(f"{base}/patients/{b['patient_id']}/consents").status_code == 404
    assert client.post(f"{base}/medications", json={"patient_id": a["patient_id"], "name": "X", "dose": "1", "frequency": "d", "start_date": future_date}).status_code == 403


def test_appointment_conflict_and_patient_detail(client):
    a = _new_clinic_with_staff_and_patient(client, "ScheduleA")
    h = _use_identity(client, a["admin"])
    payload = {"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": _future_iso()}
    r = client.post("/api/v1/appointments", json=payload, headers=h)
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    assert client.post("/api/v1/appointments", json=payload, headers=h).status_code == 409
    assert client.get(f"/api/v1/appointments/{item_id}").status_code == 200
    assert client.get(f"/api/v1/patients/{a['patient_id']}").status_code == 200
    assert client.patch(f"/api/v1/patients/{a['patient_id']}", json={"phone": "123"}, headers=h).json()["phone"] == "123"
    assert client.post(f"/api/v1/appointments/{item_id}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post("/api/v1/appointments", json=payload, headers=h).status_code == 201
    payload["scheduled_at"] = (datetime.now(UTC) + timedelta(days=30)).replace(tzinfo=None, microsecond=0).isoformat()
    assert client.post("/api/v1/appointments", json=payload, headers=h).status_code == 422


def test_notifications_are_private_and_read_is_csrf_protected(client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models import User
    from app.modules.clinical.service import create_notification
    from tests.conftest import TEST_DATABASE_URL

    a = _new_clinic_with_staff_and_patient(client, "NotifyA")
    b = _new_clinic_with_staff_and_patient(client, "NotifyB")
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as db:
        recipient = db.query(User).filter(User.clinic_id == a["clinic_id"], User.role == "clinic_admin").one()
        notification_id = create_notification(db, recipient, "Aviso", "Consulta alterada", "appointment").id
        db.commit()
    engine.dispose()
    _use_identity(client, b["admin"])
    assert client.get("/api/v1/notifications").json() == []
    assert client.patch(f"/api/v1/notifications/{notification_id}/read", headers=_use_identity(client, b["admin"])).status_code == 404
    _use_identity(client, a["admin"])
    assert len(client.get("/api/v1/notifications").json()) == 1
    assert client.patch(f"/api/v1/notifications/{notification_id}/read").status_code == 403
    assert client.patch(f"/api/v1/notifications/{notification_id}/read", headers=_use_identity(client, a["admin"])).json()["is_read"] is True
