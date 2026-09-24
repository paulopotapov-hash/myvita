"""B1 appointment lifecycle, filtering, authorization and validation regressions."""
# ruff: noqa: F401, F811

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_appointments_integration import (
    _future_iso,
    _new_clinic_with_staff_and_patient,
    _use_identity,
    client,
)


def _create_appointment(client, clinic, *, days: int = 30, hours: int = 0):
    response = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": clinic["patient_id"],
            "staff_id": clinic["staff_id"],
            "scheduled_at": _future_iso(days=days, hours=hours),
        },
        headers=_use_identity(client, clinic["admin"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _patch_status(client, clinic, appointment_id: str, status: str):
    return client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"status": status},
        headers=_use_identity(client, clinic["admin"]),
    )


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        ("scheduled", "confirmed"),
        ("scheduled", "cancelled"),
        ("scheduled", "no_show"),
        ("confirmed", "completed"),
        ("confirmed", "cancelled"),
        ("confirmed", "no_show"),
    ],
)
def test_all_valid_status_transitions(client, initial, target):
    clinic = _new_clinic_with_staff_and_patient(client, f"Valid-{initial}-{target}")
    item = _create_appointment(client, clinic)
    if initial == "confirmed":
        assert _patch_status(client, clinic, item["id"], "confirmed").status_code == 200
    response = _patch_status(client, clinic, item["id"], target)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == target


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        ("scheduled", "completed"),
        ("completed", "scheduled"),
        ("completed", "cancelled"),
        ("cancelled", "scheduled"),
        ("cancelled", "confirmed"),
        ("no_show", "scheduled"),
        ("no_show", "completed"),
        ("no_show", "cancelled"),
        ("no_show", "confirmed"),
    ],
)
def test_invalid_and_terminal_status_transitions_return_conflict(client, initial, target):
    clinic = _new_clinic_with_staff_and_patient(client, f"Invalid-{initial}-{target}")
    item = _create_appointment(client, clinic)
    if initial == "completed":
        assert _patch_status(client, clinic, item["id"], "confirmed").status_code == 200
        assert _patch_status(client, clinic, item["id"], "completed").status_code == 200
    elif initial != "scheduled":
        assert _patch_status(client, clinic, item["id"], initial).status_code == 200
    response = _patch_status(client, clinic, item["id"], target)
    assert response.status_code == 409


def test_patch_validation_conflict_and_noop_behavior(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Patch")
    first = _create_appointment(client, clinic)
    second = _create_appointment(client, clinic, hours=2)
    headers = _use_identity(client, clinic["admin"])

    assert client.patch(f"/api/v1/appointments/{first['id']}", json={}, headers=headers).status_code == 422
    assert client.patch(
        f"/api/v1/appointments/{first['id']}",
        json={"scheduled_at": "2030-01-01T10:00:00"},
        headers=headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/appointments/{first['id']}", json={"duration_minutes": 4}, headers=headers
    ).status_code == 422
    conflict = client.patch(
        f"/api/v1/appointments/{second['id']}",
        json={"scheduled_at": first["scheduled_at"], "duration_minutes": first["duration_minutes"]},
        headers=headers,
    )
    assert conflict.status_code == 409

    new_time = (datetime.now(UTC) + timedelta(days=45)).replace(microsecond=0).isoformat()
    changed = client.patch(
        f"/api/v1/appointments/{first['id']}",
        json={"reason": "Seguimento", "scheduled_at": new_time, "duration_minutes": 45},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["reason"] == "Seguimento"
    assert changed.json()["duration_minutes"] == 45


def test_tenant_and_patient_idor_for_detail_patch_and_cancel(client):
    clinic_a = _new_clinic_with_staff_and_patient(client, "IdorA")
    clinic_b = _new_clinic_with_staff_and_patient(client, "IdorB")
    item_a = _create_appointment(client, clinic_a)
    item_b = _create_appointment(client, clinic_b)

    _use_identity(client, clinic_a["patient"])
    assert client.get(f"/api/v1/appointments/{item_a['id']}").status_code == 200
    assert client.get(f"/api/v1/appointments/{item_b['id']}").status_code == 404
    assert client.post(
        f"/api/v1/appointments/{item_b['id']}/cancel", headers=_use_identity(client, clinic_a["patient"])
    ).status_code == 404
    assert client.patch(
        f"/api/v1/appointments/{item_a['id']}",
        json={"reason": "proibido"},
        headers=_use_identity(client, clinic_a["patient"]),
    ).status_code == 403

    headers = _use_identity(client, clinic_a["admin"])
    assert client.get(f"/api/v1/appointments/{item_b['id']}").status_code == 404
    assert client.patch(
        f"/api/v1/appointments/{item_b['id']}", json={"reason": "x"}, headers=headers
    ).status_code == 404
    assert client.post(f"/api/v1/appointments/{item_b['id']}/cancel", headers=headers).status_code == 404

    own_cancel = client.post(
        f"/api/v1/appointments/{item_a['id']}/cancel",
        headers=_use_identity(client, clinic_a["patient"]),
    )
    assert own_cancel.status_code == 200
    assert own_cancel.json()["status"] == "cancelled"


def test_nonexistent_and_malformed_appointment_ids(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Missing")
    headers = _use_identity(client, clinic["admin"])
    assert client.get(f"/api/v1/appointments/{uuid.uuid4()}").status_code == 404
    assert client.patch(
        f"/api/v1/appointments/{uuid.uuid4()}", json={"reason": "x"}, headers=headers
    ).status_code == 404
    assert client.get("/api/v1/appointments/not-a-uuid").status_code == 422


def test_list_filters_combine_and_cannot_expand_patient_or_tenant_scope(client):
    clinic_a = _new_clinic_with_staff_and_patient(client, "FilterA")
    clinic_b = _new_clinic_with_staff_and_patient(client, "FilterB")
    first = _create_appointment(client, clinic_a, days=20)
    second = _create_appointment(client, clinic_a, days=40)
    other = _create_appointment(client, clinic_b, days=30)
    assert _patch_status(client, clinic_a, second["id"], "confirmed").status_code == 200

    _use_identity(client, clinic_a["admin"])
    params = {
        "patient_id": clinic_a["patient_id"],
        "staff_id": clinic_a["staff_id"],
        "status": "scheduled",
        "start_date": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        "end_date": (datetime.now(UTC) + timedelta(days=25)).isoformat(),
        "limit": 1,
        "offset": 0,
    }
    response = client.get("/api/v1/appointments", params=params)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first["id"]]
    assert client.get("/api/v1/appointments", params={"status": "invalid"}).status_code == 422
    assert client.get(
        "/api/v1/appointments", params={"start_date": "2030-02-01T00:00:00+00:00", "end_date": "2030-01-01T00:00:00+00:00"}
    ).status_code == 422
    assert client.get("/api/v1/appointments", params={"patient_id": "bad"}).status_code == 422
    assert client.get(
        "/api/v1/appointments", params={"patient_id": clinic_b["patient_id"]}
    ).json() == []

    _use_identity(client, clinic_a["patient"])
    assert client.get(
        "/api/v1/appointments", params={"patient_id": clinic_b["patient_id"]}
    ).json() == []
    assert all(
        item["clinic_id"] == clinic_a["clinic_id"]
        for item in client.get("/api/v1/appointments", params={"staff_id": clinic_b["staff_id"]}).json()
    )
    assert other["clinic_id"] == clinic_b["clinic_id"]


def test_nonexistent_patient_and_staff_are_hidden(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Relations")
    headers = _use_identity(client, clinic["admin"])
    base = {"scheduled_at": _future_iso(days=60)}
    assert client.post(
        "/api/v1/appointments",
        json={**base, "patient_id": str(uuid.uuid4()), "staff_id": clinic["staff_id"]},
        headers=headers,
    ).status_code == 404
    assert client.post(
        "/api/v1/appointments",
        json={**base, "patient_id": clinic["patient_id"], "staff_id": str(uuid.uuid4())},
        headers=headers,
    ).status_code == 404
