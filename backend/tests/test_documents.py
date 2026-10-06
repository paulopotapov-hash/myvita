import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.clinical_support import Tenant, audit, make_tenant


@pytest.fixture()
def tenants(client: TestClient, tmp_path, monkeypatch) -> tuple[Tenant, Tenant]:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "private-documents"))
    a = make_tenant(client, "documents-a")
    b = make_tenant(client, "documents-b")
    return a, b


def create_note(client: TestClient, tenant: Tenant, role: str = "doctor", patient_id: str | None = None):
    return client.post(
        f"/api/v1/patients/{patient_id or tenant.patient_id}/documents/notes",
        headers=tenant.act(client, role),
        json={"title": "Instruções", "content": "Seguir o plano diário."},
    )


def upload_pdf(client: TestClient, tenant: Tenant, *, name="instructions.pdf", content=b"%PDF-1.7\nexample"):
    return client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents/files",
        headers=tenant.act(client, "doctor"),
        data={"title": "Relatório"},
        files={"file": (name, BytesIO(content), "application/pdf")},
    )


def test_note_versions_authorization_notification_and_audit(client: TestClient, tenants):
    a, b = tenants
    created = create_note(client, a)
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["kind"] == "note" and document["current_version"] == 1
    assert document["current_content"] == "Seguir o plano diário."

    # Assigned nurses have the explicit Phase 1 clinical permission.
    assert (
        client.get(f"/api/v1/patients/{a.patient_id}/documents", headers=a.act(client, "nurse")).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/documents/{document['id']}", headers=a.act(client, "nurse")).status_code == 200
    )
    nurse_note = client.post(
        f"/api/v1/patients/{a.patient_id}/documents/notes",
        headers=a.act(client, "nurse"),
        json={"title": "Acompanhamento", "content": "Contactar na próxima semana."},
    )
    assert nurse_note.status_code == 201, nurse_note.text

    update = client.patch(
        f"/api/v1/documents/{document['id']}/notes",
        headers=a.act(client, "nurse"),
        json={"title": "Instruções revistas", "content": "Versão revista."},
    )
    assert update.status_code == 200, update.text
    assert update.json()["current_version"] == 2
    assert update.json()["current_content"] == "Versão revista."
    history = client.get(f"/api/v1/documents/{document['id']}/versions", headers=a.act(client, "patient"))
    assert history.status_code == 200
    assert [item["version"] for item in history.json()] == [1, 2]
    assert history.json()[0]["content"] == "Seguir o plano diário."
    assert history.json()[1]["content"] == "Versão revista."
    assert history.json()[1]["is_current"] is True
    assert history.json()[1]["author_name"] == "Nurse documents-a"

    with client.session_factory() as db:  # type: ignore[attr-defined]
        from app.models import Notification

        alerts = db.query(Notification).filter(Notification.target_id == document["id"]).all()
        assert len(alerts) == 2
        assert {row.target_type for row in alerts} == {"document"}
        assert {row.user_id for row in alerts} == {uuid.UUID(a.user_ids["patient"])}

    # Own documents visible, unrelated patient and another tenant hidden, admin/physio denied.
    assert (
        client.get("/api/v1/documents/mine", headers=a.act(client, "patient")).json()[0]["id"]
        == document["id"]
    )
    assert (
        client.get(
            f"/api/v1/patients/{a.other_patient_id}/documents", headers=a.act(client, "patient")
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/documents/{document['id']}", headers=b.act(client, "doctor")).status_code == 404
    )
    assert (
        client.get(f"/api/v1/documents/{document['id']}", headers=a.act(client, "admin")).status_code == 403
    )
    assert (
        client.get(
            f"/api/v1/documents/{document['id']}", headers=a.act(client, "physiotherapist")
        ).status_code
        == 403
    )
    assert audit(client, "document_created", resource_id=document["id"])
    assert audit(client, "document_updated", resource_id=document["id"])
    assert audit(client, "document_viewed", resource_id=document["id"])
    assert audit(client, "permission_denied", resource_id=document["id"])


def test_file_upload_download_versions_and_file_validation(client: TestClient, tenants, monkeypatch):
    a, _ = tenants
    created = upload_pdf(client, a)
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["kind"] == "file" and doc["current_version"] == 1
    history = client.get(f"/api/v1/documents/{doc['id']}/versions", headers=a.act(client, "patient"))
    assert history.status_code == 200
    assert "checksum_sha256" not in history.json()[0]
    assert "storage_key" not in history.json()[0]

    response = client.get(f"/api/v1/documents/{doc['id']}/download", headers=a.act(client, "patient"))
    assert response.status_code == 200
    assert response.content == b"%PDF-1.7\nexample"
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert audit(client, "document_downloaded", resource_id=doc["id"])

    replacement = client.post(
        f"/api/v1/documents/{doc['id']}/files/versions",
        headers=a.act(client, "nurse"),
        data={"title": "Relatório atualizado"},
        files={"file": ("updated.pdf", BytesIO(b"%PDF-1.7\nnew"), "application/pdf")},
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["current_version"] == 2
    old = client.get(f"/api/v1/documents/{doc['id']}/versions/1/download", headers=a.act(client, "patient"))
    assert old.content == b"%PDF-1.7\nexample"
    current = client.get(f"/api/v1/documents/{doc['id']}/download", headers=a.act(client, "patient"))
    assert current.content == b"%PDF-1.7\nnew"
    large_replacement = client.post(
        f"/api/v1/documents/{doc['id']}/files/versions",
        headers=a.act(client, "nurse"),
        data={"title": "Relatório grande"},
        files={"file": ("large.pdf", BytesIO(b"%PDF-1.7\n" + b"x" * 1_100_000), "application/pdf")},
    )
    assert large_replacement.status_code == 200, large_replacement.text
    assert large_replacement.json()["current_version"] == 3

    invalid = upload_pdf(client, a, name="script.exe", content=b"MZ")
    assert invalid.status_code == 422
    malicious = upload_pdf(client, a, name="../../secret.pdf")
    assert malicious.status_code == 422
    bad_signature = upload_pdf(client, a, name="fake.pdf", content=b"not a PDF")
    assert bad_signature.status_code == 422

    monkeypatch.setattr("app.modules.documents.storage.MAX_FILE_BYTES", 20)
    oversized = upload_pdf(client, a, name="large.pdf", content=b"%PDF-1.7\n" + b"x" * 50)
    assert oversized.status_code == 413


def test_document_creation_and_download_enforce_assignment_and_tenant(client: TestClient, tenants):
    a, b = tenants
    created = create_note(client, a)
    doc_id = created.json()["id"]
    denied = create_note(client, a, "doctor", a.other_patient_id)
    assert denied.status_code == 403
    assert create_note(client, b).status_code == 201
    cross = client.get(f"/api/v1/documents/{doc_id}/download", headers=b.act(client, "patient"))
    assert cross.status_code == 404
    assert audit(client, "permission_denied", resource_id=a.other_patient_id)
    assert audit(client, "permission_denied", resource_id=doc_id)


def test_upload_filename_is_metadata_only_and_storage_key_is_opaque(client: TestClient, tenants):
    a, _ = tenants
    created = upload_pdf(client, a, name="Patient report.pdf")
    assert created.status_code == 201, created.text
    doc_id = created.json()["id"]
    versions = client.get(f"/api/v1/documents/{doc_id}/versions", headers=a.act(client, "patient")).json()
    assert versions[0]["original_filename"] == "Patient report.pdf"
    assert "storage_key" not in versions[0]
    stored = list(Path(settings.DOCUMENT_STORAGE_DIR).iterdir())
    assert len(stored) == 1 and stored[0].name != "Patient report.pdf"
