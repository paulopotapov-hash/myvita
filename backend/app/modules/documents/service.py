import uuid

from sqlalchemy.orm import Session

from app.models import Document, User
from app.modules.documents.storage import BinaryReader, LocalDocumentStorage


def list_patient_documents(
    db: Session, patient_id: uuid.UUID, clinic_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[Document], int]:
    query = db.query(Document).filter(Document.patient_id == patient_id, Document.clinic_id == clinic_id)
    total = query.count()
    return query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(
        limit
    ).all(), total


def get_document(db: Session, document_id: uuid.UUID, clinic_id: uuid.UUID) -> Document | None:
    return db.query(Document).filter(Document.id == document_id, Document.clinic_id == clinic_id).first()


def persist_document(
    db: Session,
    storage: LocalDocumentStorage,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    user: User,
    filename: str,
    content_type: str,
    size: int,
    source: BinaryReader,
) -> Document:
    key = storage.new_key()
    storage.save(key, source)
    document = Document(
        clinic_id=clinic_id,
        patient_id=patient_id,
        uploaded_by_user_id=user.id,
        original_filename=filename,
        storage_key=key,
        content_type=content_type,
        file_size=size,
    )
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return document


def delete_document(db: Session, storage: LocalDocumentStorage, document: Document) -> None:
    staged_key = storage.stage_delete(document.storage_key)
    try:
        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        storage.restore_delete(document.storage_key, staged_key)
        raise
    storage.finish_delete(staged_key)
