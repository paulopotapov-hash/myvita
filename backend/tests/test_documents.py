import uuid
from io import BytesIO

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditAction, AuditLog
from app.modules.documents.storage import LocalDocumentStorage


def _upload(actor, patient_id: str, name: str = "report.pdf", content: bytes = b"%PDF-1.7\ncontent"):
    return actor.client.post(
        f"/api/v1/patients/{patient_id}/documents",
        files={"file": (name, content, "application/pdf")},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )


def test_document_upload_list_download_and_delete(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    doctor = world.a.doctor
    patient_id = world.a.patients["a1"].patient_id
    uploaded = _upload(doctor, patient_id)
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["original_filename"] == "report.pdf"
    assert metadata["content_type"] == "application/pdf"
    assert "storage_key" not in metadata
    storage = LocalDocumentStorage(tmp_path)
    assert storage.exists(next(tmp_path.iterdir()).name)

    listing = doctor.get(f"/api/v1/patients/{patient_id}/documents")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [metadata["id"]]
    assert listing.headers["x-total-count"] == "1"

    download = doctor.get(f"/api/v1/documents/{metadata['id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.7\ncontent"
    assert download.headers["content-type"].startswith("application/pdf")
    assert "filename*=UTF-8''report.pdf" in download.headers["content-disposition"]

    removed = doctor.call("DELETE", f"/api/v1/documents/{metadata['id']}")
    assert removed.status_code == 204
    assert not list(tmp_path.iterdir())
    assert doctor.get(f"/api/v1/documents/{metadata['id']}/download").status_code == 404
    with world.db() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.resource_id == metadata["id"],
                    AuditLog.action.in_(
                        [
                            AuditAction.DOCUMENT_UPLOADED,
                            AuditAction.DOCUMENT_DOWNLOADED,
                            AuditAction.DOCUMENT_DELETED,
                        ]
                    ),
                )
            )
        )
    assert actions == {
        AuditAction.DOCUMENT_UPLOADED,
        AuditAction.DOCUMENT_DOWNLOADED,
        AuditAction.DOCUMENT_DELETED,
    }


def test_document_authorization_and_tenant_isolation(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    foreign_patient = world.b.patients["b1"].patient_id
    assert _upload(world.a.doctor, foreign_patient).status_code == 404
    assert _upload(world.a.staff_admin, world.a.patients["a1"].patient_id).status_code == 403
    assert _upload(world.a.patients["a1"], world.a.patients["a1"].patient_id).status_code == 403

    created = _upload(world.b.doctor, foreign_patient)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    assert world.a.doctor.get(f"/api/v1/documents/{document_id}/download").status_code == 404
    assert world.a.doctor.call("DELETE", f"/api/v1/documents/{document_id}").status_code == 404
    assert world.a.doctor.get(f"/api/v1/patients/{foreign_patient}/documents").status_code == 404


def test_document_routes_require_authentication(world):
    anonymous = world.a.doctor.client.__class__(world.a.doctor.client.app)
    patient_id = world.a.patients["a1"].patient_id
    assert anonymous.get(f"/api/v1/patients/{patient_id}/documents").status_code == 401
    assert (
        anonymous.post(
            f"/api/v1/patients/{patient_id}/documents",
            files={"file": ("a.pdf", b"%PDF-1.7", "application/pdf")},
        ).status_code
        == 401
    )
    assert anonymous.get(f"/api/v1/documents/{uuid.uuid4()}/download").status_code == 401
    assert anonymous.delete(f"/api/v1/documents/{uuid.uuid4()}").status_code == 401


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("script.pdf", b"#!/bin/sh", "application/pdf"),
        ("bad.exe", b"MZ", "application/octet-stream"),
        ("../escape.pdf", b"%PDF-1.7", "application/pdf"),
        ("empty.pdf", b"", "application/pdf"),
    ],
)
def test_document_upload_rejects_invalid_content(world, filename, content, mime):
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        files={"file": (filename, content, mime)},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 422


def test_document_upload_enforces_configured_maximum(world, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_MAX_UPLOAD_BYTES", 1024)
    response = _upload(
        world.a.doctor,
        world.a.patients["a1"].patient_id,
        content=b"%PDF-1.7" + b"x" * 1024,
    )
    assert response.status_code == 413


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("scan.png", b"\x89PNG\r\n\x1a\nminimal", "image/png"),
        ("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg"),
    ],
)
def test_document_upload_accepts_supported_images(world, tmp_path, monkeypatch, filename, content, mime):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        files={"file": (filename, content, mime)},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == mime


def test_document_upload_rejects_missing_file(world):
    actor = world.a.doctor
    response = actor.post(f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents")
    assert response.status_code == 422


def test_private_storage_rejects_path_keys_and_does_not_overwrite(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage.new_key()
    storage.save(key, BytesIO(b"safe"))
    with pytest.raises(FileExistsError):
        storage.save(key, BytesIO(b"overwrite"))
    with pytest.raises(ValueError):
        storage.open("../escape")
    assert storage.open(key).read() == b"safe"
