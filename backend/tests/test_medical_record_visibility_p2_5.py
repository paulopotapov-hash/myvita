"""P2.5 — what a patient can see of their medical history, who decides it, and nothing more.

P2.6 — the "record shared" notification is covered here too, because it is a
consequence of the sharing decision itself.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models import MedicalRecord, MedicalRecordRevision, MedicalRecordVisibility, Notification
from app.modules.notifications.events import TEMPLATES, NotificationEvent
from tests.clinical_support import Tenant, audit, make_tenant, prescribe, use

PATIENT_RECORD_KEYS = {"view", "id", "author_name", "title", "content", "created_at", "updated_at"}
INTERNAL_NOTE = "Suspeita de abuso de substâncias, não partilhar"
SHARED_TITLE = "Plano terapêutico de oncologia"
SHARED_CONTENT = "Iniciar quimioterapia adjuvante"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "visibility")


def _record(client: TestClient, tenant: Tenant, content: str, *, title: str = "Consulta", **extra) -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        headers=tenant.act(client, "doctor"),
        json={"title": title, "content": content, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _share(client: TestClient, tenant: Tenant, record_id: str, version: int, role: str = "doctor"):
    return client.post(
        f"/api/v1/medical-records/{record_id}/share",
        headers=tenant.act(client, role),
        json={"expected_version": version},
    )


def _unshare(client: TestClient, tenant: Tenant, record_id: str, role: str = "doctor"):
    return client.post(f"/api/v1/medical-records/{record_id}/unshare", headers=tenant.act(client, role))


def _notifications(client: TestClient, user_id: str | None = None) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        query = db.query(Notification).order_by(Notification.created_at, Notification.id)
        if user_id is not None:
            query = query.filter(Notification.user_id == uuid.UUID(user_id))
        rows = query.all()
        for row in rows:
            db.expunge(row)
        return rows


def _legacy_record(client: TestClient, tenant: Tenant, content: str = "Nota anterior ao P2.5") -> str:
    """A record as migration 6b7c8d9e0f1a leaves pre-existing rows: legacy_shared, no decision author."""
    record_id = uuid.uuid4()
    with client.session_factory() as db:  # type: ignore[attr-defined]
        db.add(
            MedicalRecord(
                id=record_id,
                clinic_id=uuid.UUID(tenant.clinic_id),
                patient_id=uuid.UUID(tenant.patient_id),
                author_staff_id=uuid.UUID(tenant.staff_ids["doctor"]),
                title="Consulta antiga",
                content=content,
                patient_visibility=MedicalRecordVisibility.LEGACY_SHARED,
                version=1,
            )
        )
        db.flush()
        db.add(
            MedicalRecordRevision(
                record_id=record_id,
                editor_staff_id=uuid.UUID(tenant.staff_ids["doctor"]),
                version=1,
                title="Consulta antiga",
                content=content,
                patient_visibility=MedicalRecordVisibility.LEGACY_SHARED,
            )
        )
        db.commit()
    return str(record_id)


def test_records_are_internal_by_default_and_hidden_from_the_patient(client: TestClient, tenant: Tenant):
    internal = _record(client, tenant, INTERNAL_NOTE)
    assert internal["visibility"] == "internal"
    assert internal["visibility_changed_at"] is None and internal["visibility_changed_by_name"] is None
    shared = _record(client, tenant, "Plano terapêutico partilhado", share_with_patient=True)
    assert shared["visibility"] == "shared"
    assert shared["visibility_changed_by_name"] == "Doctor visibility"
    assert shared["visibility_changed_at"]

    tenant.act(client, "patient")
    listing = client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records")
    assert listing.status_code == 200
    assert listing.headers["X-Total-Count"] == "1"
    assert [row["id"] for row in listing.json()] == [shared["id"]]
    assert INTERNAL_NOTE not in listing.text
    # An internal record answers exactly like a missing one.
    hidden = client.get(f"/api/v1/medical-records/{internal['id']}")
    missing = client.get(f"/api/v1/medical-records/{uuid.uuid4()}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert audit(client, "permission_denied", resource_id=internal["id"])

    # The care team still sees both.
    tenant.act(client, "nurse")
    staff_listing = client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").json()
    assert {row["id"] for row in staff_listing} == {internal["id"], shared["id"]}
    assert all(row["view"] == "staff" for row in staff_listing)


def test_patient_view_exposes_only_approved_fields(client: TestClient, tenant: Tenant):
    shared = _record(client, tenant, "Partilhado", share_with_patient=True)
    tenant.act(client, "patient")
    (row,) = client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").json()
    assert set(row) == PATIENT_RECORD_KEYS
    assert row["view"] == "patient"
    assert row["author_name"] == "Doctor visibility"
    detail = client.get(f"/api/v1/medical-records/{shared['id']}")
    assert set(detail.json()) == PATIENT_RECORD_KEYS
    for internal in (tenant.staff_ids["doctor"], tenant.clinic_id):
        assert internal not in detail.text
    assert not {"visibility", "version", "visibility_changed_by_name"} & set(detail.json())
    # Edit history is internal, even for a shared record, and answers like a missing record.
    revisions = client.get(f"/api/v1/medical-records/{shared['id']}/revisions")
    assert revisions.status_code == 404
    assert revisions.json() == client.get(f"/api/v1/medical-records/{uuid.uuid4()}/revisions").json()


def test_sharing_is_explicit_versioned_audited_and_notified_once(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, SHARED_CONTENT, title=SHARED_TITLE)
    assert _notifications(client) == []
    url = f"/api/v1/medical-records/{record['id']}"

    shared = _share(client, tenant, record["id"], 1, role="nurse")
    assert shared.status_code == 200, shared.text
    assert shared.json()["visibility"] == "shared"
    assert shared.json()["version"] == 2
    assert shared.json()["visibility_changed_by_name"] == "Nurse visibility"

    # Exactly one generic notification, to the record's own patient, deep-linked to the record.
    (notification,) = _notifications(client)
    assert str(notification.user_id) == tenant.user_ids["patient"]
    assert str(notification.clinic_id) == tenant.clinic_id
    assert (notification.title, notification.message) == TEMPLATES[NotificationEvent.MEDICAL_RECORD_SHARED]
    assert notification.target_type == "medical_record"
    assert str(notification.record_target_id) == record["id"]
    assert notification.target_id is None and notification.result_target_id is None
    for secret in (SHARED_TITLE, SHARED_CONTENT, "oncologia", "quimioterapia"):
        assert secret not in f"{notification.title} {notification.message}"

    (row,) = audit(client, "medical_record_shared", resource_id=record["id"])
    assert str(row.actor_user_id) == tenant.user_ids["nurse"]
    assert row.event_metadata["from"] == "internal" and row.event_metadata["to"] == "shared"
    assert SHARED_CONTENT not in str(row.event_metadata)

    # A repeated request is not a new sharing event: no revision, audit row or notification.
    again = _share(client, tenant, record["id"], 1)
    assert again.status_code == 200 and again.json()["version"] == 2
    assert len(_notifications(client)) == 1
    assert len(audit(client, "medical_record_shared", resource_id=record["id"])) == 1

    # The deep link resolves through the normal, access-checked endpoint.
    tenant.act(client, "patient")
    (api_notification,) = client.get("/api/v1/notifications").json()
    assert api_notification["target_type"] == "medical_record"
    assert api_notification["record_target_id"] == record["id"]
    assert "event_key" not in api_notification
    assert client.get(url).json()["content"] == SHARED_CONTENT


def test_unsharing_revokes_access_immediately_even_from_an_old_notification(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, "Nota", share_with_patient=True)
    (notification,) = _notifications(client, tenant.user_ids["patient"])
    url = f"/api/v1/medical-records/{record['id']}"
    tenant.act(client, "patient")
    assert client.get(url).status_code == 200

    unshared = _unshare(client, tenant, record["id"])
    assert unshared.status_code == 200, unshared.text
    assert unshared.json()["visibility"] == "internal"
    (row,) = audit(client, "medical_record_unshared", resource_id=record["id"])
    assert row.event_metadata["from"] == "shared" and row.event_metadata["to"] == "internal"

    tenant.act(client, "patient")
    # The old notification is still listed (generic text) but opens nothing.
    assert [n["record_target_id"] for n in client.get("/api/v1/notifications").json()] == [record["id"]]
    assert client.get(url).status_code == 404
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").json() == []
    assert client.post(f"/api/v1/notifications/{notification.id}/read", headers=use(client, tenant.who["patient"])).status_code == 200
    assert client.get(url).status_code == 404

    # Unsharing an internal record changes nothing.
    assert _unshare(client, tenant, record["id"]).json()["version"] == unshared.json()["version"]
    assert len(audit(client, "medical_record_unshared", resource_id=record["id"])) == 1

    # Sharing it again is a new sharing event: a second notification.
    reshared = _share(client, tenant, record["id"], unshared.json()["version"])
    assert reshared.status_code == 200
    assert len(_notifications(client, tenant.user_ids["patient"])) == 2


def test_edits_never_change_visibility_and_history_is_kept(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, "Nota")
    headers = tenant.act(client, "doctor")
    url = f"/api/v1/medical-records/{record['id']}"

    # A visibility field on an edit is refused outright, and nothing changes.
    for field in ("patient_visible", "share_with_patient", "visibility", "patient_visibility"):
        refused = client.patch(url, headers=headers, json={"title": "Consulta", "content": "Nota", "expected_version": 1, field: True})
        assert refused.status_code == 422, field
    assert client.get(url).json()["version"] == 1

    assert _share(client, tenant, record["id"], 1).status_code == 200
    edited = client.patch(url, headers=tenant.act(client, "doctor"), json={"title": "Consulta", "content": "Nota revista", "expected_version": 2})
    assert edited.status_code == 200
    assert edited.json()["visibility"] == "shared"
    # Editing a shared record is not a new sharing event.
    assert len(_notifications(client)) == 1
    tenant.act(client, "patient")
    assert client.get(url).json()["content"] == "Nota revista"

    assert _unshare(client, tenant, record["id"]).status_code == 200
    tenant.act(client, "doctor")
    revisions = client.get(f"{url}/revisions").json()
    assert [(row["version"], row["visibility"], row["editor_name"]) for row in revisions] == [
        (1, "internal", "Doctor visibility"),
        (2, "shared", "Doctor visibility"),
        (3, "shared", "Doctor visibility"),
        (4, "internal", "Doctor visibility"),
    ]
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(MedicalRecordRevision).filter(MedicalRecordRevision.record_id == uuid.UUID(record["id"])).count() == 4


def test_sharing_requires_the_reviewed_version_but_unsharing_never_waits(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, "Versão revista pelo médico")
    url = f"/api/v1/medical-records/{record['id']}"
    edited = client.patch(url, headers=tenant.act(client, "nurse"), json={"title": "Consulta", "content": "Acrescento interno", "expected_version": 1})
    assert edited.status_code == 200

    # The doctor reviewed version 1; sharing it would publish content they have not seen.
    stale = _share(client, tenant, record["id"], 1)
    assert stale.status_code == 409
    assert _notifications(client) == []
    assert audit(client, "medical_record_shared") == []
    tenant.act(client, "patient")
    assert client.get(url).status_code == 404

    assert _share(client, tenant, record["id"], 2).status_code == 200
    client.patch(url, headers=tenant.act(client, "nurse"), json={"title": "Consulta", "content": "Outra edição", "expected_version": 3})
    # Withdrawing access is never refused for a stale version.
    assert _unshare(client, tenant, record["id"]).json()["visibility"] == "internal"


@pytest.mark.parametrize("role", ["clinic_admin", "admin", "physiotherapist"])
def test_only_assigned_clinicians_can_share_or_unshare(client: TestClient, tenant: Tenant, role: str):
    record = _record(client, tenant, "Nota")
    shared = _record(client, tenant, "Partilhada", share_with_patient=True)
    before = len(_notifications(client))
    assert _share(client, tenant, record["id"], 1, role=role).status_code == 403
    assert _unshare(client, tenant, shared["id"], role=role).status_code == 403
    assert audit(client, "permission_denied", resource_id=record["id"])
    assert len(_notifications(client)) == before


def test_patients_unassigned_staff_and_other_clinics_cannot_change_visibility(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, INTERNAL_NOTE)
    shared = _record(client, tenant, "Partilhada", share_with_patient=True)
    before = len(_notifications(client))

    # The patient cannot share an internal note with themselves, nor unshare.
    assert _share(client, tenant, record["id"], 1, role="patient").status_code == 404
    assert _unshare(client, tenant, shared["id"], role="patient").status_code == 404
    assert _share(client, tenant, record["id"], 1, role="other_patient").status_code == 404

    client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['nurse']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    assert _share(client, tenant, record["id"], 1, role="nurse").status_code == 403
    assert _unshare(client, tenant, shared["id"], role="nurse").status_code == 403

    other = make_tenant(client, "visibility-c")
    for role in ("doctor", "nurse"):
        assert client.post(
            f"/api/v1/medical-records/{record['id']}/share", headers=other.act(client, role), json={"expected_version": 1}
        ).status_code == 404
        assert client.post(f"/api/v1/medical-records/{shared['id']}/unshare", headers=other.act(client, role)).status_code == 404

    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/medical-records/{record['id']}").json()["visibility"] == "internal"
    assert client.get(f"/api/v1/medical-records/{shared['id']}").json()["visibility"] == "shared"
    assert len(_notifications(client)) == before


def test_legacy_records_keep_patient_access_without_a_fabricated_decision(client: TestClient, tenant: Tenant):
    legacy_id = _legacy_record(client, tenant)
    url = f"/api/v1/medical-records/{legacy_id}"

    # The patient keeps the access the previous policy gave them, and no one was notified.
    tenant.act(client, "patient")
    assert client.get(url).status_code == 200
    assert [row["id"] for row in client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").json()] == [legacy_id]
    assert _notifications(client) == []

    # Staff see it as legacy access, not as somebody's sharing decision.
    tenant.act(client, "doctor")
    staff_view = client.get(url).json()
    assert staff_view["visibility"] == "legacy_shared"
    assert staff_view["visibility_changed_at"] is None and staff_view["visibility_changed_by_name"] is None

    # Confirming it records an explicit decision but does not notify (nothing new for the patient).
    confirmed = _share(client, tenant, legacy_id, 1)
    assert confirmed.json()["visibility"] == "shared"
    assert confirmed.json()["visibility_changed_by_name"] == "Doctor visibility"
    (row,) = audit(client, "medical_record_shared", resource_id=legacy_id)
    assert row.event_metadata["from"] == "legacy_shared"
    assert _notifications(client) == []


def test_withdrawing_legacy_access_is_final(client: TestClient, tenant: Tenant):
    legacy_id = _legacy_record(client, tenant)
    withdrawn = _unshare(client, tenant, legacy_id)
    assert withdrawn.json()["visibility"] == "internal"
    (row,) = audit(client, "medical_record_unshared", resource_id=legacy_id)
    assert row.event_metadata["from"] == "legacy_shared"
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/medical-records/{legacy_id}").status_code == 404
    # Sharing again is an explicit share (and a notification), never a return to legacy access.
    assert _share(client, tenant, legacy_id, withdrawn.json()["version"]).json()["visibility"] == "shared"
    assert len(_notifications(client, tenant.user_ids["patient"])) == 1


def test_other_patients_and_other_clinics_never_see_a_shared_record(client: TestClient, tenant: Tenant):
    shared = _record(client, tenant, "Partilhado", share_with_patient=True)
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/medical-records/{shared['id']}").status_code == 404
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").status_code == 404
    assert client.get("/api/v1/notifications").json() == []

    other = make_tenant(client, "visibility-b")
    for role in ("doctor", "nurse", "patient", "clinic_admin"):
        other.act(client, role)
        assert client.get(f"/api/v1/medical-records/{shared['id']}").status_code == 404, role
        assert client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").status_code == 404, role


@pytest.mark.parametrize("role", ["clinic_admin", "admin", "physiotherapist"])
def test_administering_a_clinic_grants_no_clinical_content(client: TestClient, tenant: Tenant, role: str):
    shared = _record(client, tenant, "Partilhado", share_with_patient=True)
    tenant.act(client, role)
    for path in (
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        f"/api/v1/medical-records/{shared['id']}",
        f"/api/v1/medical-records/{shared['id']}/revisions",
        f"/api/v1/patients/{tenant.patient_id}/medications",
        f"/api/v1/patients/{tenant.patient_id}/results",
        f"/api/v1/patients/{tenant.patient_id}/documents",
    ):
        assert client.get(path).status_code == 403, path


def test_unassigned_professionals_cannot_read_records(client: TestClient, tenant: Tenant):
    record = _record(client, tenant, "Nota")
    client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['nurse']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    tenant.act(client, "nurse")
    assert client.get(f"/api/v1/medical-records/{record['id']}").status_code == 403
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").status_code == 403
    assert client.get(f"/api/v1/medical-records/{record['id']}/revisions").status_code == 403


def test_patient_history_sections_stay_available(client: TestClient, tenant: Tenant):
    """Regression: medications and documents remain patient-visible with their own checks."""
    medication = prescribe(client, tenant)
    upload = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents",
        headers=tenant.act(client, "doctor"),
        data={"title": "Relatório"},
        files={"file": ("r.pdf", b"%PDF-1.7\nreport", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    tenant.act(client, "patient")
    assert [row["id"] for row in client.get(f"/api/v1/patients/{tenant.patient_id}/medications").json()] == [medication["id"]]
    assert [row["id"] for row in client.get(f"/api/v1/patients/{tenant.patient_id}/documents").json()] == [upload.json()["id"]]
    assert client.get(f"/api/v1/documents/{upload.json()['id']}/download").status_code == 200
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/documents/{upload.json()['id']}/download").status_code == 404
    assert client.get(f"/api/v1/medications/{medication['id']}").status_code == 404
