"""P2.4 — clinical results: professional workflow, patient access, isolation, audit, notifications."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import ClinicalResult, Notification
from app.modules.notifications.events import TEMPLATES, NotificationEvent
from tests.clinical_support import Tenant, audit, make_tenant, use

SECRET_TITLE = "Marcador tumoral CA-125"
SECRET_VALUE = "812"
SECRET_SUMMARY = "Valor muito elevado, sugestivo de neoplasia"

PATIENT_VIEW_KEYS = {
    "view",
    "id",
    "category",
    "title",
    "value",
    "unit",
    "reference_range",
    "summary",
    "result_date",
    "document_id",
    "author_name",
    "released_at",
    "corrects_result_id",
    "superseded_by_result_id",
}


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "results")


def _payload(**overrides) -> dict:
    return {
        "category": "laboratory",
        "title": SECRET_TITLE,
        "value": SECRET_VALUE,
        "unit": "U/mL",
        "reference_range": "< 35",
        "summary": SECRET_SUMMARY,
        "result_date": "2026-01-15",
        **overrides,
    }


def _create(client: TestClient, tenant: Tenant, role: str = "doctor", for_patient: str | None = None, **overrides):
    return client.post(
        f"/api/v1/patients/{for_patient or tenant.patient_id}/results",
        headers=tenant.act(client, role),
        json=_payload(**overrides),
    )


def _notifications_for(client: TestClient, user_id: str) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(Notification).filter(Notification.user_id == uuid.UUID(user_id)).all()
        for row in rows:
            db.expunge(row)
        return rows


def _upload_document(client: TestClient, tenant: Tenant, patient_id: str) -> str:
    response = client.post(
        f"/api/v1/patients/{patient_id}/documents",
        headers=tenant.act(client, "doctor"),
        data={"title": "Relatório do laboratório"},
        files={"file": ("lab.pdf", b"%PDF-1.7\nlab report", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_doctor_creates_a_draft_that_the_patient_cannot_see(client: TestClient, tenant: Tenant):
    created = _create(client, tenant)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["view"] == "staff"
    assert body["status"] == "draft"
    assert body["patient_id"] == tenant.patient_id
    assert body["author_name"] == "Doctor results"
    assert body["released_at"] is None and body["released_by_name"] is None
    # Internal staff ids are never exposed; display names are.
    assert "author_staff_id" not in body and "clinic_id" not in body

    tenant.act(client, "patient")
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results").json() == []
    assert client.get(f"/api/v1/results/{body['id']}").status_code == 404
    # A draft never notifies anyone.
    assert _notifications_for(client, tenant.user_ids["patient"]) == []


def test_release_makes_the_result_visible_and_notifies_the_patient_once(client: TestClient, tenant: Tenant):
    result_id = _create(client, tenant).json()["id"]

    released = client.post(f"/api/v1/results/{result_id}/release", headers=tenant.act(client, "nurse"))
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"
    assert released.json()["released_by_name"] == "Nurse results"
    assert released.json()["released_at"]

    # Release is one-way and idempotent in effect: a second release is a conflict.
    again = client.post(f"/api/v1/results/{result_id}/release", headers=tenant.act(client, "doctor"))
    assert again.status_code == 409

    notifications = _notifications_for(client, tenant.user_ids["patient"])
    assert len(notifications) == 1
    notification = notifications[0]
    assert (notification.title, notification.message) == TEMPLATES[NotificationEvent.RESULT_AVAILABLE]
    assert notification.target_type == "result"
    assert str(notification.result_target_id) == result_id
    assert notification.target_id is None and notification.conversation_target_id is None
    assert str(notification.clinic_id) == tenant.clinic_id
    text = f"{notification.title} {notification.message}"
    for secret in (SECRET_TITLE, SECRET_VALUE, SECRET_SUMMARY, "U/mL", "laboratory", "laborat"):
        assert secret not in text
    # Nobody else is notified.
    assert _notifications_for(client, tenant.user_ids["other_patient"]) == []
    assert _notifications_for(client, tenant.user_ids["doctor"]) == []

    tenant.act(client, "patient")
    listed = client.get(f"/api/v1/patients/{tenant.patient_id}/results")
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    (item,) = listed.json()
    assert set(item) == PATIENT_VIEW_KEYS
    assert item["view"] == "patient"
    assert item["value"] == SECRET_VALUE and item["unit"] == "U/mL"
    detail = client.get(f"/api/v1/results/{result_id}")
    assert detail.status_code == 200
    assert set(detail.json()) == PATIENT_VIEW_KEYS

    # The notification deep link resolves through the normal, authorized endpoint.
    api_notification = client.get("/api/v1/notifications").json()[0]
    assert api_notification["target_type"] == "result"
    assert api_notification["result_target_id"] == result_id
    assert "event_key" not in api_notification


def test_create_and_release_in_one_step_audits_both(client: TestClient, tenant: Tenant):
    created = _create(client, tenant, release=True)
    assert created.status_code == 201, created.text
    result_id = created.json()["id"]
    assert created.json()["status"] == "released"
    assert len(_notifications_for(client, tenant.user_ids["patient"])) == 1

    for action in ("clinical_result_created", "clinical_result_released"):
        (row,) = audit(client, action, resource_id=result_id)
        assert str(row.actor_user_id) == tenant.user_ids["doctor"]
        assert str(row.clinic_id) == tenant.clinic_id
        assert row.event_metadata["patient_id"] == tenant.patient_id
        assert row.event_metadata["status"] == "released"
        # Identifiers and workflow state only, never clinical content.
        dumped = str(row.event_metadata)
        for secret in (SECRET_TITLE, SECRET_VALUE, SECRET_SUMMARY):
            assert secret not in dumped

    tenant.act(client, "patient")
    assert client.get(f"/api/v1/results/{result_id}").status_code == 200
    assert len(audit(client, "clinical_result_viewed", resource_id=result_id)) == 1


def test_drafts_can_be_edited_but_released_results_are_immutable(client: TestClient, tenant: Tenant):
    result_id = _create(client, tenant).json()["id"]
    edited = client.patch(
        f"/api/v1/results/{result_id}",
        headers=tenant.act(client, "doctor"),
        json={"value": "30", "summary": None},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["value"] == "30" and edited.json()["summary"] is None
    assert len(audit(client, "clinical_result_draft_updated", resource_id=result_id)) == 1

    # Removing every piece of content is refused and leaves the draft untouched.
    emptied = client.patch(
        f"/api/v1/results/{result_id}",
        headers=tenant.act(client, "doctor"),
        json={"value": None, "unit": None, "reference_range": None},
    )
    assert emptied.status_code == 422
    assert client.get(f"/api/v1/results/{result_id}").json()["value"] == "30"

    assert client.post(f"/api/v1/results/{result_id}/release", headers=tenant.act(client, "doctor")).status_code == 200
    frozen = client.patch(
        f"/api/v1/results/{result_id}", headers=tenant.act(client, "doctor"), json={"value": "31"}
    )
    assert frozen.status_code == 409
    assert client.get(f"/api/v1/results/{result_id}").json()["value"] == "30"


@pytest.mark.parametrize("role", ["physiotherapist", "admin", "clinic_admin"])
def test_roles_without_result_permission_are_denied(client: TestClient, tenant: Tenant, role: str):
    result_id = _create(client, tenant).json()["id"]
    assert _create(client, tenant, role=role).status_code == 403
    tenant.act(client, role)
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results").status_code == 403
    assert client.get(f"/api/v1/results/{result_id}").status_code == 403
    assert client.post(f"/api/v1/results/{result_id}/release", headers=tenant.act(client, role)).status_code == 403
    # Denials are audited against the requested resource.
    assert audit(client, "permission_denied", resource_id=result_id)
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalResult).count() == 1


def test_patients_cannot_write_or_read_other_patients_results(client: TestClient, tenant: Tenant):
    result_id = _create(client, tenant, release=True).json()["id"]

    # The patient cannot create results, even on their own record.
    tenant.act(client, "patient")
    assert _create(client, tenant, role="patient").status_code in {403, 404}
    assert client.patch(
        f"/api/v1/results/{result_id}", headers=use(client, tenant.who["patient"]), json={"value": "1"}
    ).status_code in {403, 404}

    # Another patient of the same clinic: same answer as a missing result (no existence oracle).
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results").status_code == 404
    assert client.get(f"/api/v1/results/{result_id}").status_code == 404
    assert client.get(f"/api/v1/results/{uuid.uuid4()}").status_code == 404


def test_professional_access_requires_an_active_care_assignment(client: TestClient, tenant: Tenant):
    # other_patient has no care team at all.
    assert _create(client, tenant, for_patient=tenant.other_patient_id).status_code == 403

    result_id = _create(client, tenant).json()["id"]
    ended = client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['doctor']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    assert ended.status_code == 200, ended.text
    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/results/{result_id}").status_code == 403
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results").status_code == 403
    assert client.post(f"/api/v1/results/{result_id}/release", headers=tenant.act(client, "doctor")).status_code == 403
    # The nurse, still assigned, keeps access.
    tenant.act(client, "nurse")
    assert client.get(f"/api/v1/results/{result_id}").status_code == 200


def test_cross_clinic_access_is_impossible(client: TestClient, tenant: Tenant):
    other = make_tenant(client, "results-b")
    result_id = _create(client, tenant, release=True).json()["id"]
    for role in ("doctor", "nurse", "patient", "clinic_admin"):
        other.act(client, role)
        assert client.get(f"/api/v1/results/{result_id}").status_code == 404, role
        assert client.get(f"/api/v1/patients/{tenant.patient_id}/results").status_code == 404, role
    assert _create(client, other, for_patient=tenant.patient_id).status_code == 404


def test_invalid_input_is_rejected_without_side_effects(client: TestClient, tenant: Tenant):
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    invalid = (
        {"title": "   "},
        {"title": "x" * 201},
        {"category": "genetic"},
        {"result_date": tomorrow},
        {"value": None, "summary": None},
        {"value": None, "summary": "Sem valor", "unit": "mg"},
        {"summary": "x" * 5001},
        {"clinic_id": str(uuid.uuid4())},
        {"patient_id": tenant.other_patient_id},
        {"status": "released"},
        {"author_staff_id": tenant.staff_ids["nurse"]},
    )
    for overrides in invalid:
        assert _create(client, tenant, **overrides).status_code == 422, overrides
    # A linked document must exist and belong to this patient.
    assert _create(client, tenant, document_id=str(uuid.uuid4())).status_code == 422
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalResult).count() == 0
    assert audit(client, "clinical_result_created") == []


def test_a_document_of_another_patient_cannot_be_attached(client: TestClient, tenant: Tenant):
    # Put the doctor on other_patient's care team too, so only the document rule can refuse.
    assigned = client.post(
        f"/api/v1/patients/{tenant.other_patient_id}/care-team",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"]},
    )
    assert assigned.status_code == 201, assigned.text
    other_patients_document = _upload_document(client, tenant, tenant.other_patient_id)
    attached = _create(client, tenant, document_id=other_patients_document)
    assert attached.status_code == 422
    assert "document" in attached.text.lower() or "documento" in attached.text.lower()
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalResult).count() == 0
    assert audit(client, "clinical_result_created") == []


def test_result_can_reference_a_document_of_the_same_patient(client: TestClient, tenant: Tenant):
    document_id = _upload_document(client, tenant, tenant.patient_id)
    created = _create(client, tenant, value=None, unit=None, reference_range=None, summary=None, document_id=document_id)
    assert created.status_code == 201, created.text
    assert created.json()["document_id"] == document_id
    client.post(f"/api/v1/results/{created.json()['id']}/release", headers=tenant.act(client, "doctor"))

    # The document keeps its own access rules: the patient downloads it through the documents API.
    tenant.act(client, "patient")
    result = client.get(f"/api/v1/results/{created.json()['id']}").json()
    assert result["document_id"] == document_id
    assert client.get(f"/api/v1/documents/{document_id}/download").status_code == 200
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/documents/{document_id}/download").status_code == 404


def test_listing_is_paginated_newest_clinical_date_first(client: TestClient, tenant: Tenant):
    for day in ("2026-01-01", "2026-03-01", "2026-02-01"):
        assert _create(client, tenant, result_date=day, release=True).status_code == 201
    assert _create(client, tenant, result_date="2026-04-01").status_code == 201  # draft

    tenant.act(client, "doctor")
    staff_page = client.get(f"/api/v1/patients/{tenant.patient_id}/results?page_size=2")
    assert staff_page.headers["X-Total-Count"] == "4"
    assert [row["result_date"] for row in staff_page.json()] == ["2026-04-01", "2026-03-01"]
    drafts = client.get(f"/api/v1/patients/{tenant.patient_id}/results?status=draft")
    assert [row["status"] for row in drafts.json()] == ["draft"]
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results?page_size=101").status_code == 422

    tenant.act(client, "patient")
    first = client.get(f"/api/v1/patients/{tenant.patient_id}/results?page=1&page_size=2")
    second = client.get(f"/api/v1/patients/{tenant.patient_id}/results?page=2&page_size=2")
    assert first.headers["X-Total-Count"] == "3"
    assert [row["result_date"] for row in first.json() + second.json()] == ["2026-03-01", "2026-02-01", "2026-01-01"]
    # Asking for drafts as a patient yields nothing, never the drafts.
    assert client.get(f"/api/v1/patients/{tenant.patient_id}/results?status=draft").json() == []


# --- Corrections and immutability of released results ---------------------------------

CORRECTION_REASON = "Erro de transcrição do valor laboratorial"


def _correct(client: TestClient, tenant: Tenant, result_id: str, role: str = "doctor", **overrides):
    body = {**_payload(value="35"), "correction_reason": CORRECTION_REASON, **overrides}
    return client.post(f"/api/v1/results/{result_id}/corrections", headers=tenant.act(client, role), json=body)


def _row(client: TestClient, result_id: str) -> dict:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        row = db.get(ClinicalResult, uuid.UUID(result_id))
        return {column: getattr(row, column) for column in ("title", "value", "summary", "status", "released_at", "updated_at")}


def test_a_correction_is_a_new_linked_result_and_the_original_is_preserved(client: TestClient, tenant: Tenant):
    original_id = _create(client, tenant, release=True).json()["id"]
    original_before = _row(client, original_id)

    correction = _correct(client, tenant, original_id)
    assert correction.status_code == 201, correction.text
    body = correction.json()
    assert body["id"] != original_id
    assert body["status"] == "draft"
    assert body["corrects_result_id"] == original_id
    assert body["correction_reason"] == CORRECTION_REASON
    assert body["value"] == "35"
    # The released original is untouched, and the correction is linked from it.
    assert _row(client, original_id) == original_before
    original = client.get(f"/api/v1/results/{original_id}").json()
    assert original["corrected_by_result_id"] == body["id"]
    assert original["superseded"] is False

    (row,) = audit(client, "clinical_result_corrected", resource_id=body["id"])
    assert row.event_metadata["corrects_result_id"] == original_id
    assert CORRECTION_REASON not in str(row.event_metadata)

    # A draft correction is invisible to the patient, who still sees the original only.
    tenant.act(client, "patient")
    (only,) = client.get(f"/api/v1/patients/{tenant.patient_id}/results").json()
    assert only["id"] == original_id and only["superseded_by_result_id"] is None
    assert client.get(f"/api/v1/results/{body['id']}").status_code == 404
    assert len(_notifications_for(client, tenant.user_ids["patient"])) == 1  # the original release only

    # Releasing the correction notifies once, with the generic "corrected" text.
    released = client.post(f"/api/v1/results/{body['id']}/release", headers=tenant.act(client, "nurse"))
    assert released.status_code == 200, released.text
    notifications = _notifications_for(client, tenant.user_ids["patient"])
    assert [(n.title, n.message) for n in notifications] == [
        TEMPLATES[NotificationEvent.RESULT_AVAILABLE],
        TEMPLATES[NotificationEvent.RESULT_CORRECTED],
    ]
    assert str(notifications[1].result_target_id) == body["id"]
    assert CORRECTION_REASON not in notifications[1].message

    tenant.act(client, "patient")
    listed = {row["id"]: row for row in client.get(f"/api/v1/patients/{tenant.patient_id}/results").json()}
    assert set(listed) == {original_id, body["id"]}
    assert listed[original_id]["superseded_by_result_id"] == body["id"]
    assert listed[original_id]["value"] == SECRET_VALUE  # what the patient was shown is kept
    assert listed[body["id"]]["corrects_result_id"] == original_id
    # The professional's internal reason is not part of the patient view.
    assert all(set(row) == PATIENT_VIEW_KEYS for row in listed.values())
    assert CORRECTION_REASON not in client.get(f"/api/v1/results/{body['id']}").text
    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/results/{original_id}").json()["superseded"] is True


def test_corrections_require_a_released_result_a_reason_and_form_a_chain(client: TestClient, tenant: Tenant):
    draft_id = _create(client, tenant).json()["id"]
    refused = _correct(client, tenant, draft_id)
    assert refused.status_code == 409
    (denied,) = audit(client, "clinical_result_corrected", resource_id=draft_id)
    assert denied.result.value == "denied" and denied.event_metadata["reason"] == "not_released"

    original_id = _create(client, tenant, release=True).json()["id"]
    for reason in (None, "", "   ", "abc", "  ab  ", "x" * 1001):
        overrides = {"correction_reason": reason} if reason is not None else {}
        body = {**_payload(value="35"), **overrides}
        if reason is None:
            body.pop("correction_reason", None)
        response = client.post(f"/api/v1/results/{original_id}/corrections", headers=tenant.act(client, "doctor"), json=body)
        assert response.status_code == 422, reason
    # The patient is the original's patient: the body cannot choose one, nor a status or an author.
    for field, value in (
        ("patient_id", tenant.other_patient_id),
        ("status", "released"),
        ("corrects_result_id", draft_id),
        ("author_staff_id", tenant.staff_ids["nurse"]),
    ):
        assert _correct(client, tenant, original_id, **{field: value}).status_code == 422, field

    first = _correct(client, tenant, original_id, release=True)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "released"
    assert first.json()["patient_id"] == tenant.patient_id
    for action in ("clinical_result_corrected", "clinical_result_released"):
        assert len(audit(client, action, resource_id=first.json()["id"])) == 1
    # The original is corrected once; the next correction applies to the latest version.
    second = _correct(client, tenant, original_id)
    assert second.status_code == 409
    assert audit(client, "clinical_result_corrected", resource_id=original_id)[-1].event_metadata["reason"] == "already_corrected"
    chained = _correct(client, tenant, first.json()["id"], value="36")
    assert chained.status_code == 201
    assert chained.json()["corrects_result_id"] == first.json()["id"]
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalResult).filter(ClinicalResult.corrects_result_id == uuid.UUID(original_id)).count() == 1


def test_draft_corrections_can_be_edited_including_the_reason(client: TestClient, tenant: Tenant):
    original_id = _create(client, tenant, release=True).json()["id"]
    correction_id = _correct(client, tenant, original_id).json()["id"]
    edited = client.patch(
        f"/api/v1/results/{correction_id}",
        headers=tenant.act(client, "doctor"),
        json={"value": "34", "correction_reason": "Valor reconfirmado com o laboratório"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["correction_reason"] == "Valor reconfirmado com o laboratório"
    assert client.patch(f"/api/v1/results/{correction_id}", headers=tenant.act(client, "doctor"), json={"correction_reason": None}).status_code == 422
    # A result that is not a correction has no reason to edit.
    other_draft = _create(client, tenant).json()["id"]
    assert client.patch(
        f"/api/v1/results/{other_draft}", headers=tenant.act(client, "doctor"), json={"correction_reason": "Motivo inventado"}
    ).status_code == 422


def test_released_results_are_immutable_on_every_path_and_refusals_are_audited(client: TestClient, tenant: Tenant):
    result_id = _create(client, tenant, release=True).json()["id"]
    before = _row(client, result_id)
    headers = tenant.act(client, "doctor")
    for payload in ({"value": "1"}, {"title": "Outro"}, {"document_id": None}, {"result_date": "2026-01-01"}):
        assert client.patch(f"/api/v1/results/{result_id}", headers=headers, json=payload).status_code == 409
    assert client.post(f"/api/v1/results/{result_id}/release", headers=headers).status_code == 409
    # No endpoint deletes or replaces a result.
    assert client.delete(f"/api/v1/results/{result_id}", headers=headers).status_code == 405
    assert client.put(f"/api/v1/results/{result_id}", headers=headers, json=_payload()).status_code == 405
    assert _row(client, result_id) == before

    denied = [row for row in audit(client, "clinical_result_draft_updated", resource_id=result_id)]
    assert len(denied) == 4 and all(row.result.value == "denied" for row in denied)
    assert all(row.event_metadata["reason"] == "released_immutable" for row in denied)
    assert [row.result.value for row in audit(client, "clinical_result_released", resource_id=result_id)] == ["success", "denied"]


def test_the_orm_guard_stops_any_code_path_from_rewriting_a_released_result(client: TestClient, tenant: Tenant):
    from app.models.clinical_result import ReleasedResultImmutableError

    released_id = uuid.UUID(_create(client, tenant, release=True).json()["id"])
    draft_id = uuid.UUID(_create(client, tenant).json()["id"])
    with client.session_factory() as db:  # type: ignore[attr-defined]
        released = db.get(ClinicalResult, released_id)
        db.commit()  # expire everything: the guard must not rely on loaded state
        released.value = "999"
        with pytest.raises(ReleasedResultImmutableError):
            db.flush()
        db.rollback()
        db.delete(db.get(ClinicalResult, released_id))
        with pytest.raises(ReleasedResultImmutableError):
            db.flush()
        db.rollback()
        # Drafts stay editable through the ORM.
        draft = db.get(ClinicalResult, draft_id)
        draft.value = "41"
        db.commit()
    assert _row(client, str(released_id))["value"] == SECRET_VALUE
    assert _row(client, str(draft_id))["value"] == "41"


def test_corrections_follow_the_same_access_rules(client: TestClient, tenant: Tenant):
    original_id = _create(client, tenant, release=True).json()["id"]
    for role in ("physiotherapist", "admin", "clinic_admin"):
        assert _correct(client, tenant, original_id, role=role).status_code == 403, role
    assert _correct(client, tenant, original_id, role="patient").status_code == 404
    assert _correct(client, tenant, original_id, role="other_patient").status_code == 404
    other = make_tenant(client, "results-corr-b")
    assert client.post(
        f"/api/v1/results/{original_id}/corrections",
        headers=other.act(client, "doctor"),
        json={**_payload(), "correction_reason": CORRECTION_REASON},
    ).status_code == 404
    client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['doctor']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    assert _correct(client, tenant, original_id, role="doctor").status_code == 403
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalResult).count() == 1
    assert audit(client, "clinical_result_corrected") == []
    assert len(_notifications_for(client, tenant.user_ids["patient"])) == 1


def test_the_database_rejects_any_update_or_delete_of_a_released_result(client: TestClient, tenant: Tenant):
    """Migration 8d9e0f1a2b3c: the trigger covers paths the ORM flush guard cannot see
    (bulk ORM updates, raw SQL), while drafts stay editable."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    released_id = _create(client, tenant, release=True).json()["id"]
    draft_id = _create(client, tenant).json()["id"]
    before = _row(client, released_id)
    with client.session_factory() as db:  # type: ignore[attr-defined]
        for statement in (
            "UPDATE clinical_results SET value = '1' WHERE id = :id",
            "UPDATE clinical_results SET status = 'draft', released_at = NULL, released_by_staff_id = NULL WHERE id = :id",
            "UPDATE clinical_results SET updated_at = now() WHERE id = :id",
            "DELETE FROM clinical_results WHERE id = :id",
        ):
            with pytest.raises(DBAPIError) as excinfo:
                db.execute(text(statement), {"id": released_id})
            assert excinfo.value.orig.sqlstate == "42501", statement
            assert "released and immutable" in str(excinfo.value.orig)
            db.rollback()
        # A bulk ORM update bypasses the flush guard, but not the database.
        with pytest.raises(DBAPIError):
            db.query(ClinicalResult).filter(ClinicalResult.id == uuid.UUID(released_id)).update(
                {"value": "999"}, synchronize_session=False
            )
        db.rollback()
        # Drafts remain editable and deletable at the database level.
        db.execute(text("UPDATE clinical_results SET value = '42' WHERE id = :id"), {"id": draft_id})
        db.commit()
    assert _row(client, released_id) == before
    assert _row(client, draft_id)["value"] == "42"
