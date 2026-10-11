"""Clinical history (commit 3, decisions D1-D9).

Covers: partial dates; category rules (API and database CHECKs); origin and
confirmation; the patient's own declarations (D3); hiding from the patient with a
reason (D4); soft delete with reason; optimistic versions and revisions; the
permission matrix and tenant isolation; audit rows and logs without clinical
content; declared medication with optional dose (D6). Synthetic data only.
"""

import json
import logging
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.partial_dates import PartialDateError, format_partial_date, parse_partial_date
from app.models import AuditAction, AuditLog, ClinicalHistoryEntry, ClinicalHistoryRevision, DatePrecision
from tests.clinical_support import Tenant, make_tenant

CONTENT = ("Asma sintética", "Penicilina sintética", "Urticária sintética", "Nota clínica sintética", "Motivo sintético")


def _url(tenant: Tenant, patient_id: str | None = None) -> str:
    return f"/api/v1/patients/{patient_id or tenant.patient_id}/clinical-history"


def _create(client: TestClient, tenant: Tenant, role: str, **payload) -> dict:
    response = client.post(_url(tenant), headers=tenant.act(client, role), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _audit_rows(client: TestClient, *actions: AuditAction) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action.in_(actions)).order_by(AuditLog.timestamp).all()


def _row_text(row: AuditLog) -> str:
    return json.dumps({column.name: str(getattr(row, column.key)) for column in AuditLog.__table__.columns})


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"history-{uuid.uuid4().hex[:8]}")


# --- partial dates (D5) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stored", "precision"),
    [
        ("2010", date(2010, 1, 1), DatePrecision.YEAR),
        ("2010-03", date(2010, 3, 1), DatePrecision.MONTH),
        ("2010-03-12", date(2010, 3, 12), DatePrecision.DAY),
    ],
)
def test_partial_dates_keep_their_precision(raw: str, stored: date, precision: DatePrecision):
    assert parse_partial_date(raw, today=date(2026, 10, 11)) == (stored, precision)
    assert format_partial_date(stored, precision) == raw


@pytest.mark.parametrize("raw", ["10-03-2010", "2010-13", "2010-02-30", "1899", "2027", "2026-11", "abc"])
def test_invalid_partial_dates_are_refused(raw: str):
    with pytest.raises(PartialDateError):
        parse_partial_date(raw, today=date(2026, 10, 11))


# --- category rules -----------------------------------------------------------------------------


def test_each_category_stores_its_own_fields(client: TestClient, tenant: Tenant):
    condition = _create(
        client, tenant, "doctor", category="condition", name="Asma sintética", condition_status="resolved",
        onset="2010", resolved="2015-03",
    )
    assert (condition["onset"], condition["resolved"], condition["condition_status"]) == ("2010", "2015-03", "resolved")
    procedure = _create(client, tenant, "nurse", category="procedure", name="Apendicectomia", occurred="2012-06-20", location="Hospital Sintético")
    assert (procedure["occurred"], procedure["location"]) == ("2012-06-20", "Hospital Sintético")
    allergy = _create(client, tenant, "doctor", category="allergy", name="Penicilina sintética", reaction="Urticária sintética", severity="severe")
    assert allergy["severity"] == "severe"
    vaccine = _create(client, tenant, "doctor", category="immunization", name="Tétano", occurred="2020-05")
    note = _create(client, tenant, "doctor", category="note", note_text="Nota clínica sintética")
    for entry in (condition, procedure, allergy, vaccine, note):
        assert entry["view"] == "staff"
        assert (entry["origin"], entry["confirmed"]) == ("professional", True)
        assert entry["confirmed_by_name"] and entry["version"] == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"category": "allergy", "name": "X"}, "severity"),
        ({"category": "note"}, "note_text"),
        ({"category": "condition", "name": "X"}, "condition_status"),
        ({"category": "immunization", "name": "X", "location": "Y"}, "location"),
        ({"category": "note", "note_text": "X", "name": "Y"}, "name"),
        ({"category": "condition", "name": "X", "condition_status": "active", "resolved": "2015"}, "resolved"),
        ({"category": "condition", "name": "X", "condition_status": "resolved", "onset": "2015", "resolved": "2010"}, "resolved"),
        ({"category": "procedure", "name": "X", "occurred": "2999"}, "occurred"),
        ({"category": "procedure", "name": "  "}, "name"),
    ],
)
def test_category_rules_name_the_wrong_field(client: TestClient, tenant: Tenant, payload: dict, field: str):
    response = client.post(_url(tenant), headers=tenant.act(client, "doctor"), json=payload)
    assert response.status_code == 422, response.text
    assert field in {error["loc"][-1] for error in response.json()["detail"]}


def test_database_checks_refuse_incoherent_rows(client: TestClient, tenant: Tenant):
    """The CHECK constraints hold even if the service were bypassed."""
    base = {
        "id": uuid.uuid4(), "clinic": tenant.clinic_id, "patient": tenant.patient_id, "user": tenant.user_ids["patient"],
    }
    statements = [
        # an allergy without severity
        "INSERT INTO clinical_history_entries (id, clinic_id, patient_id, category, name, origin, created_by_user_id, version) "
        "VALUES (:id, :clinic, :patient, 'allergy', 'X', 'patient_declared', :user, 1)",
        # a year-precision date that is not the first day of the year
        "INSERT INTO clinical_history_entries (id, clinic_id, patient_id, category, name, occurred_on, occurred_precision, "
        "origin, created_by_user_id, version) VALUES (:id, :clinic, :patient, 'immunization', 'X', '2010-03-12', 'year', "
        "'patient_declared', :user, 1)",
        # a professional entry that is not confirmed
        "INSERT INTO clinical_history_entries (id, clinic_id, patient_id, category, note_text, origin, created_by_user_id, version) "
        "VALUES (:id, :clinic, :patient, 'note', 'X', 'professional', :user, 1)",
    ]
    for statement in statements:
        with client.session_factory() as db:  # type: ignore[attr-defined]
            with pytest.raises(IntegrityError):
                db.execute(text(statement), base)
                db.flush()


# --- declarations, confirmation and versions (D3) -------------------------------------------------


def test_patient_declares_edits_until_confirmed_then_only_professionals_change_it(client: TestClient, tenant: Tenant):
    declared = _create(client, tenant, "patient", category="allergy", name="Penicilina sintética", severity="unknown")
    assert declared["view"] == "patient"
    assert (declared["origin"], declared["confirmed"], declared["can_edit"]) == ("patient_declared", False, True)
    assert "created_by_name" not in declared and "hidden" not in declared

    edited = client.patch(
        f"/api/v1/clinical-history/{declared['id']}",
        headers=tenant.act(client, "patient"),
        json={"reaction": "Urticária sintética", "expected_version": 1},
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2

    stale = client.post(
        f"/api/v1/clinical-history/{declared['id']}/confirm", headers=tenant.act(client, "nurse"), json={"expected_version": 1}
    )
    assert stale.status_code == 409
    confirmed = client.post(
        f"/api/v1/clinical-history/{declared['id']}/confirm", headers=tenant.act(client, "nurse"), json={"expected_version": 2}
    )
    assert confirmed.status_code == 200
    assert (confirmed.json()["origin"], confirmed.json()["confirmed"]) == ("patient_declared", True)

    patient_headers = tenant.act(client, "patient")
    seen = client.get(f"/api/v1/clinical-history/{declared['id']}").json()
    assert (seen["confirmed"], seen["can_edit"]) == (True, False)
    for method, path, body in (
        ("PATCH", "", {"reaction": "X", "expected_version": 3}),
        ("POST", "/delete", {"expected_version": 3}),
    ):
        response = client.request(method, f"/api/v1/clinical-history/{declared['id']}{path}", headers=patient_headers, json=body)
        assert response.status_code == 403, response.text

    # The professional may still correct it.
    corrected = client.patch(
        f"/api/v1/clinical-history/{declared['id']}",
        headers=tenant.act(client, "doctor"),
        json={"severity": "moderate", "expected_version": 3},
    )
    assert corrected.status_code == 200 and corrected.json()["severity"] == "moderate"


def test_patient_removes_an_unconfirmed_declaration_but_never_a_professional_entry(client: TestClient, tenant: Tenant):
    declared = _create(client, tenant, "patient", category="immunization", name="Gripe", occurred="2024")
    professional = _create(client, tenant, "doctor", category="note", note_text="Nota clínica sintética")
    headers = tenant.act(client, "patient")
    assert client.post(f"/api/v1/clinical-history/{professional['id']}/delete", headers=headers, json={"expected_version": 1}).status_code == 403
    assert client.post(f"/api/v1/clinical-history/{declared['id']}/delete", headers=headers, json={"expected_version": 1}).status_code == 200
    assert client.get(f"/api/v1/clinical-history/{declared['id']}").status_code == 404
    assert [entry["id"] for entry in client.get(_url(tenant)).json()] == [professional["id"]]


def test_professional_delete_requires_a_reason_and_keeps_the_row_and_its_history(client: TestClient, tenant: Tenant):
    entry = _create(client, tenant, "doctor", category="condition", name="Asma sintética", condition_status="active")
    headers = tenant.act(client, "doctor")
    without = client.post(f"/api/v1/clinical-history/{entry['id']}/delete", headers=headers, json={"expected_version": 1})
    assert without.status_code == 422
    deleted = client.post(
        f"/api/v1/clinical-history/{entry['id']}/delete", headers=headers, json={"expected_version": 1, "reason": "Motivo sintético"}
    )
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/clinical-history/{entry['id']}").status_code == 404
    assert client.get(_url(tenant)).json() == []
    with client.session_factory() as db:  # type: ignore[attr-defined]
        row = db.get(ClinicalHistoryEntry, uuid.UUID(entry["id"]))
        assert row is not None and row.deleted_at is not None and row.deletion_reason == "Motivo sintético"
        kinds = [r.change_kind.value for r in db.query(ClinicalHistoryRevision).filter_by(entry_id=row.id).order_by("version")]
        assert kinds == ["created", "deleted"]


# --- hiding from the patient (D4) ---------------------------------------------------------------


def test_hidden_entries_disappear_for_the_patient_and_show_their_reason_to_the_team(client: TestClient, tenant: Tenant):
    entry = _create(client, tenant, "doctor", category="condition", name="Asma sintética", condition_status="active")
    headers = tenant.act(client, "doctor")
    assert client.post(f"/api/v1/clinical-history/{entry['id']}/hide", headers=headers, json={"expected_version": 1, "reason": " "}).status_code == 422
    hidden = client.post(
        f"/api/v1/clinical-history/{entry['id']}/hide", headers=headers, json={"expected_version": 1, "reason": "Motivo sintético"}
    )
    assert hidden.status_code == 200
    staff_view = client.get(_url(tenant)).json()[0]
    assert (staff_view["hidden"], staff_view["hidden_reason"]) == (True, "Motivo sintético")
    assert staff_view["hidden_by_name"]

    tenant.act(client, "patient")
    assert client.get(_url(tenant)).json() == []
    assert client.get(f"/api/v1/clinical-history/{entry['id']}").status_code == 404

    shown = client.post(f"/api/v1/clinical-history/{entry['id']}/show", headers=tenant.act(client, "nurse"), json={"expected_version": 2})
    assert shown.status_code == 200 and shown.json()["hidden"] is False
    tenant.act(client, "patient")
    assert [item["id"] for item in client.get(_url(tenant)).json()] == [entry["id"]]

    revisions = client.get(f"/api/v1/clinical-history/{entry['id']}/revisions", headers=tenant.act(client, "doctor")).json()
    assert [(r["version"], r["change_kind"], r["change_reason"]) for r in revisions] == [
        (1, "created", None),
        (2, "hidden", "Motivo sintético"),
        (3, "shown", None),
    ]
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/clinical-history/{entry['id']}/revisions").status_code == 404


# --- permissions and isolation --------------------------------------------------------------------


def test_permission_matrix_and_tenant_isolation(client: TestClient, tenant: Tenant):
    other = make_tenant(client, f"history-other-{uuid.uuid4().hex[:8]}")
    entry = _create(client, tenant, "doctor", category="note", note_text="Nota clínica sintética")
    body = {"category": "note", "note_text": "X"}

    for role in ("physiotherapist", "admin", "clinic_admin"):
        headers = tenant.act(client, role)
        assert client.get(_url(tenant)).status_code == 403, role
        assert client.post(_url(tenant), headers=headers, json=body).status_code == 403, role
        assert client.get(f"/api/v1/clinical-history/{entry['id']}").status_code == 403, role
        assert client.post(f"/api/v1/clinical-history/{entry['id']}/confirm", headers=headers, json={"expected_version": 1}).status_code == 403

    # A doctor without an active care assignment for that patient.
    headers = tenant.act(client, "doctor")
    assert client.get(_url(tenant, tenant.other_patient_id)).status_code == 403
    assert client.post(_url(tenant, tenant.other_patient_id), headers=headers, json=body).status_code == 403

    # The other patient of the same clinic and every role of another clinic: it does not exist.
    tenant.act(client, "other_patient")
    assert client.get(_url(tenant)).status_code == 404
    assert client.get(f"/api/v1/clinical-history/{entry['id']}").status_code == 404
    for role in ("doctor", "patient", "clinic_admin"):
        headers = other.act(client, role)
        assert client.get(_url(tenant)).status_code == 404
        assert client.get(f"/api/v1/clinical-history/{entry['id']}").status_code == 404
        assert client.patch(f"/api/v1/clinical-history/{entry['id']}", headers=headers, json={"note_text": "X", "expected_version": 1}).status_code == 404

    # The patient sees the entry but may not confirm, hide or show anything (403).
    headers = tenant.act(client, "patient")
    for action in ("confirm", "show"):
        assert client.post(f"/api/v1/clinical-history/{entry['id']}/{action}", headers=headers, json={"expected_version": 1}).status_code == 403
    assert client.post(f"/api/v1/clinical-history/{entry['id']}/hide", headers=headers, json={"expected_version": 1, "reason": "X"}).status_code == 403

    denied = _audit_rows(client, AuditAction.PERMISSION_DENIED)
    assert any(row.resource_type == "clinical_history_entry" for row in denied)


# --- audit and logs -------------------------------------------------------------------------------


def test_every_change_is_audited_without_clinical_content(client: TestClient, tenant: Tenant, caplog):
    with caplog.at_level(logging.DEBUG):
        declared = _create(client, tenant, "patient", category="allergy", name="Penicilina sintética", severity="unknown")
        client.patch(
            f"/api/v1/clinical-history/{declared['id']}",
            headers=tenant.act(client, "patient"),
            json={"reaction": "Urticária sintética", "expected_version": 1},
        )
        headers = tenant.act(client, "doctor")
        client.post(f"/api/v1/clinical-history/{declared['id']}/confirm", headers=headers, json={"expected_version": 2})
        client.post(f"/api/v1/clinical-history/{declared['id']}/hide", headers=headers, json={"expected_version": 3, "reason": "Motivo sintético"})
        client.post(f"/api/v1/clinical-history/{declared['id']}/show", headers=headers, json={"expected_version": 4})
        note = _create(client, tenant, "doctor", category="note", note_text="Nota clínica sintética")
        client.post(f"/api/v1/clinical-history/{note['id']}/delete", headers=tenant.act(client, "doctor"), json={"expected_version": 1, "reason": "Motivo sintético"})
        tenant.act(client, "patient")
        client.get(_url(tenant))

    actions = [
        AuditAction.CLINICAL_HISTORY_DECLARED,
        AuditAction.CLINICAL_HISTORY_UPDATED,
        AuditAction.CLINICAL_HISTORY_CONFIRMED,
        AuditAction.CLINICAL_HISTORY_HIDDEN,
        AuditAction.CLINICAL_HISTORY_SHOWN,
        AuditAction.CLINICAL_HISTORY_CREATED,
        AuditAction.CLINICAL_HISTORY_DELETED,
        AuditAction.CLINICAL_HISTORY_VIEWED,
    ]
    rows = _audit_rows(client, *actions)
    assert [row.action for row in rows] == actions
    updated = rows[1]
    assert updated.event_metadata == {"patient_id": tenant.patient_id, "category": "allergy", "fields": ["reaction"]}
    assert updated.actor_user_id is not None and str(updated.resource_id) == declared["id"]
    for row in rows:
        text_of_row = _row_text(row)
        for content in CONTENT:
            assert content not in text_of_row

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "/clinical-history" in logged  # the request log was captured, so the check below means something
    for content in CONTENT:
        assert content not in logged


# --- medication: declarations, confirmation with dose, hiding, soft delete (D6, D8) ------------


def _medications(tenant: Tenant) -> str:
    return f"/api/v1/patients/{tenant.patient_id}/medications"


def test_declared_medication_flow(client: TestClient, tenant: Tenant):
    declared = client.post(
        _medications(tenant), headers=tenant.act(client, "patient"), json={"name": "Ibuprofeno sintético", "start_date": "2026-01-01"}
    )
    assert declared.status_code == 201, declared.text
    body = declared.json()
    assert (body["dosage"], body["origin"], body["confirmed"], body["can_edit"]) == (None, "patient_declared", False, True)

    headers = tenant.act(client, "patient")
    assert client.patch(f"/api/v1/medications/{body['id']}", headers=headers, json={"frequency": "SOS"}).status_code == 200
    assert client.patch(f"/api/v1/medications/{body['id']}", headers=headers, json={"status": "completed"}).status_code == 403

    # A professional must give the dose; on confirmation they may complete the patient's.
    missing = client.post(_medications(tenant), headers=tenant.act(client, "doctor"), json={"name": "X", "start_date": "2026-01-01"})
    assert missing.status_code == 422 and missing.json()["detail"][0]["loc"][-1] == "dosage"
    confirmed = client.post(f"/api/v1/medications/{body['id']}/confirm", headers=tenant.act(client, "doctor"), json={"dosage": "400 mg"})
    assert confirmed.status_code == 200
    assert (confirmed.json()["dosage"], confirmed.json()["confirmed"]) == ("400 mg", True)
    assert client.post(f"/api/v1/medications/{body['id']}/confirm", headers=tenant.act(client, "doctor")).status_code == 409

    headers = tenant.act(client, "patient")
    assert client.patch(f"/api/v1/medications/{body['id']}", headers=headers, json={"frequency": "X"}).status_code == 403
    assert client.post(f"/api/v1/medications/{body['id']}/delete", headers=headers).status_code == 403

    headers = tenant.act(client, "nurse")
    assert client.post(f"/api/v1/medications/{body['id']}/hide", headers=headers, json={"reason": "Motivo sintético"}).status_code == 200
    staff_row = client.get(_medications(tenant)).json()[0]
    assert (staff_row["hidden"], staff_row["hidden_reason"]) == (True, "Motivo sintético")
    tenant.act(client, "patient")
    assert client.get(_medications(tenant)).json() == []
    assert client.get(f"/api/v1/medications/{body['id']}").status_code == 404
    assert client.post(f"/api/v1/medications/{body['id']}/show", headers=tenant.act(client, "doctor")).status_code == 200

    headers = tenant.act(client, "doctor")
    assert client.post(f"/api/v1/medications/{body['id']}/delete", headers=headers).status_code == 422
    assert client.post(f"/api/v1/medications/{body['id']}/delete", headers=headers, json={"reason": "Motivo sintético"}).status_code == 200
    assert client.get(f"/api/v1/medications/{body['id']}").status_code == 404
    tenant.act(client, "patient")
    assert client.get(_medications(tenant)).json() == []

    actions = [row.action for row in _audit_rows(
        client,
        AuditAction.MEDICATION_DECLARED,
        AuditAction.MEDICATION_CONFIRMED,
        AuditAction.MEDICATION_HIDDEN,
        AuditAction.MEDICATION_SHOWN,
        AuditAction.MEDICATION_DELETED,
    )]
    assert actions == [
        AuditAction.MEDICATION_DECLARED,
        AuditAction.MEDICATION_CONFIRMED,
        AuditAction.MEDICATION_HIDDEN,
        AuditAction.MEDICATION_SHOWN,
        AuditAction.MEDICATION_DELETED,
    ]


def test_patient_removes_own_unconfirmed_medication_declaration(client: TestClient, tenant: Tenant):
    declared = client.post(_medications(tenant), headers=tenant.act(client, "patient"), json={"name": "X", "start_date": "2026-01-01"}).json()
    assert client.post(f"/api/v1/medications/{declared['id']}/delete", headers=tenant.act(client, "patient")).status_code == 200
    assert client.get(_medications(tenant)).json() == []
