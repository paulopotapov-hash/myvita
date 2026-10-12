"""The automatic care-team link belongs to the appointment that created it.

- Booking records that appointment as the link's origin.
- Cancelling it ends the link (audited), unless another active appointment with the same
  professional remains: that one becomes the origin.
- Moving the appointment to another professional ends the old link and creates the new one.
- Links assigned by an admin are never ended by a cancellation; an admin assigning a
  professional already linked by a booking makes that link permanent.
Synthetic data only.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models import AuditAction, AuditLog, ClinicalCareAssignment
from tests.clinical_support import Tenant, make_tenant


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"origin-{uuid.uuid4().hex[:8]}")


def _book(client: TestClient, tenant: Tenant, at: str, *, staff: str = "doctor", patient: str | None = None) -> str:
    response = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": patient or tenant.other_patient_id, "staff_id": tenant.staff_ids[staff], "scheduled_at": at},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _cancel(client: TestClient, tenant: Tenant, appointment_id: str) -> None:
    response = client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=tenant.act(client, "admin"))
    assert response.status_code == 200, response.text


def _links(client: TestClient, tenant: Tenant, staff: str = "doctor", patient: str | None = None) -> list[ClinicalCareAssignment]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return (
            db.query(ClinicalCareAssignment)
            .filter_by(patient_id=uuid.UUID(patient or tenant.other_patient_id), staff_id=uuid.UUID(tenant.staff_ids[staff]))
            .order_by(ClinicalCareAssignment.created_at)
            .all()
        )


def _ended_audits(client: TestClient) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action == AuditAction.CARE_ASSIGNMENT_ENDED).all()


def test_cancelling_the_booking_ends_the_link_it_created_and_audits_it(client: TestClient, tenant: Tenant):
    appointment_id = _book(client, tenant, "2030-04-01T10:00:00Z")
    [link] = _links(client, tenant)
    assert link.active and str(link.origin_appointment_id) == appointment_id
    assert client.get(f"/api/v1/patients/{tenant.other_patient_id}", headers=tenant.act(client, "doctor")).status_code == 200

    _cancel(client, tenant, appointment_id)
    [link] = _links(client, tenant)
    assert not link.active and link.ended_at is not None
    [audit] = _ended_audits(client)
    assert audit.resource_id == link.id
    assert {key: audit.event_metadata[key] for key in ("patient_id", "staff_id", "appointment_id", "via")} == {
        "patient_id": tenant.other_patient_id,
        "staff_id": tenant.staff_ids["doctor"],
        "appointment_id": appointment_id,
        "via": "appointment_cancelled",
    }
    # Identifiers only: no names, reasons or times.
    assert set(audit.event_metadata) <= {"patient_id", "staff_id", "appointment_id", "via", "actor_staff_role"}
    # The professional no longer reaches that patient's file.
    assert client.get(f"/api/v1/patients/{tenant.other_patient_id}", headers=tenant.act(client, "doctor")).status_code in {403, 404}

    # Booking again creates a fresh link with the new origin.
    again = _book(client, tenant, "2030-04-08T10:00:00Z")
    links = _links(client, tenant)
    assert [row.active for row in links] == [False, True]
    assert str(links[1].origin_appointment_id) == again


def test_another_active_appointment_with_the_same_professional_keeps_the_link(client: TestClient, tenant: Tenant):
    first = _book(client, tenant, "2030-04-01T10:00:00Z")
    second = _book(client, tenant, "2030-04-02T10:00:00Z")
    [link] = _links(client, tenant)
    assert str(link.origin_appointment_id) == first

    _cancel(client, tenant, first)
    [link] = _links(client, tenant)
    assert link.active and str(link.origin_appointment_id) == second
    assert _ended_audits(client) == []

    _cancel(client, tenant, second)
    [link] = _links(client, tenant)
    assert not link.active
    assert len(_ended_audits(client)) == 1


def test_a_link_assigned_by_an_admin_is_never_ended_by_a_cancellation(client: TestClient, tenant: Tenant):
    # tenant.patient has the doctor on the care team by an admin's assignment.
    appointment_id = _book(client, tenant, "2030-04-01T10:00:00Z", patient=tenant.patient_id)
    [link] = _links(client, tenant, patient=tenant.patient_id)
    assert link.origin_appointment_id is None

    _cancel(client, tenant, appointment_id)
    [link] = _links(client, tenant, patient=tenant.patient_id)
    assert link.active
    assert _ended_audits(client) == []


def test_an_admin_assignment_makes_a_booking_link_permanent(client: TestClient, tenant: Tenant):
    appointment_id = _book(client, tenant, "2030-04-01T10:00:00Z")
    assigned = client.post(
        f"/api/v1/patients/{tenant.other_patient_id}/care-team",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"]},
    )
    assert assigned.status_code == 201, assigned.text
    [link] = _links(client, tenant)
    assert link.active and link.origin_appointment_id is None and str(link.id) == assigned.json()["id"]

    _cancel(client, tenant, appointment_id)
    [link] = _links(client, tenant)
    assert link.active
    # Assigning again is still a conflict.
    again = client.post(
        f"/api/v1/patients/{tenant.other_patient_id}/care-team",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"]},
    )
    assert again.status_code == 409


def test_moving_the_appointment_to_another_professional_moves_the_link(client: TestClient, tenant: Tenant):
    appointment_id = _book(client, tenant, "2030-04-01T10:00:00Z")
    moved = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        headers=tenant.act(client, "admin"),
        json={"staff_id": tenant.staff_ids["nurse"]},
    )
    assert moved.status_code == 200, moved.text
    [doctor_link] = _links(client, tenant, "doctor")
    [nurse_link] = _links(client, tenant, "nurse")
    assert not doctor_link.active
    assert nurse_link.active and str(nurse_link.origin_appointment_id) == appointment_id
    [audit] = _ended_audits(client)
    assert audit.event_metadata["via"] == "appointment_moved"
    assert audit.event_metadata["staff_id"] == tenant.staff_ids["doctor"]
