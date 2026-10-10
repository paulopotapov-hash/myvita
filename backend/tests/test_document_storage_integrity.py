"""Document storage consistency (docs/clinical-documents.md, "Storage"):
a failed write leaves no partial file and no database row, downloads are never
cached, and the storage health signal reflects a read-only store."""

import os
import uuid
from io import BytesIO

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Document, Notification
from app.modules.documents.storage import LocalDocumentStorage
from tests.phase1_world import fresh_patient


class _FailingSource:
    """A body that breaks half-way through, like a dropped connection or an I/O error."""

    def __init__(self) -> None:
        self.calls = 0

    def read(self, size: int = -1) -> bytes:
        self.calls += 1
        if self.calls == 1:
            return b"%PDF-1.7\npartial"
        raise OSError("simulated read failure")


def test_a_failed_write_leaves_no_partial_file(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage.new_key()
    with pytest.raises(OSError):
        storage.save(key, _FailingSource())
    assert not storage.exists(key)
    assert list(tmp_path.iterdir()) == []


def test_a_key_collision_never_touches_the_existing_object(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage.new_key()
    storage.save(key, BytesIO(b"%PDF-1.7\noriginal"))
    with pytest.raises(FileExistsError):
        storage.save(key, BytesIO(b"%PDF-1.7\nother"))
    with storage.open(key) as stored:
        assert stored.read() == b"%PDF-1.7\noriginal"


def test_storage_health_reflects_a_read_only_store(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    assert storage.is_writable() is True
    os.chmod(tmp_path, 0o500)
    try:
        if os.geteuid() == 0:  # root ignores permission bits; the check is meaningless there
            pytest.skip("running as root")
        assert storage.is_writable() is False
    finally:
        os.chmod(tmp_path, 0o700)


def _setup(world, label: str):
    doctor = world.a.doctor
    patient = fresh_patient(world, world.a, label)
    assigned = world.a.admin.post(f"/api/v1/patients/{patient.patient_id}/care-team", json={"staff_id": doctor.staff_id})
    assert assigned.status_code == 201, assigned.text
    return doctor, patient


def _counts(world, patient_id: str) -> tuple[int, int]:
    with world.db() as db:
        documents = db.scalar(select(func.count(Document.id)).where(Document.patient_id == uuid.UUID(patient_id)))
        notifications = db.scalar(select(func.count(Notification.id)).where(Notification.target_type == "document"))
        return documents or 0, notifications or 0


def test_a_disk_failure_during_upload_leaves_neither_file_nor_row(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    doctor, patient = _setup(world, "docs-disk-failure")
    documents_before, notifications_before = _counts(world, patient.patient_id)

    def failing_fsync(_fd: int) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr("app.modules.documents.storage.os.fsync", failing_fsync)
    response = doctor.client.post(
        f"/api/v1/patients/{patient.patient_id}/documents",
        data={"title": "Relatório"},
        files={"file": ("r.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
        headers={settings.CSRF_HEADER_NAME: doctor.csrf_token or ""},
    )
    assert response.status_code == 503
    assert str(tmp_path) not in response.text
    assert list(tmp_path.iterdir()) == []
    assert _counts(world, patient.patient_id) == (documents_before, notifications_before)


def test_downloads_are_attachments_that_are_never_cached(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    doctor, patient = _setup(world, "docs-no-store")
    uploaded = doctor.client.post(
        f"/api/v1/patients/{patient.patient_id}/documents",
        data={"title": "Relatório"},
        files={"file": ("r.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
        headers={settings.CSRF_HEADER_NAME: doctor.csrf_token or ""},
    )
    assert uploaded.status_code == 201, uploaded.text
    download = doctor.get(f"/api/v1/documents/{uploaded.json()['id']}/download")
    assert download.status_code == 200
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("attachment;")
