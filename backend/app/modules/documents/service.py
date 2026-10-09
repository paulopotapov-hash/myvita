import uuid

from sqlalchemy.orm import Session

from app.models import Document, Notification, User
from app.modules.documents.schemas import DocumentPublic
from app.modules.documents.storage import BinaryReader, LocalDocumentStorage

# Deliberately generic: notifications live outside the document access rules,
# so no title, filename or clinical content goes into them.
NEW_DOCUMENT_NOTIFICATION_TITLE = "Novo documento"
NEW_DOCUMENT_NOTIFICATION_MESSAGE = "A equipa clínica partilhou um novo documento. Abra os documentos para o consultar."


def to_public(document: Document, uploaded_by_name: str) -> DocumentPublic:
    return DocumentPublic(
        id=document.id,
        patient_id=document.patient_id,
        title=document.title,
        uploaded_by_name=uploaded_by_name,
        original_filename=document.original_filename,
        content_type=document.content_type,
        file_size=document.file_size,
        created_at=document.created_at,
    )


def list_patient_documents(
    db: Session, patient_id: uuid.UUID, clinic_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[DocumentPublic], int]:
    query = (
        db.query(Document, User.full_name)
        .join(User, User.id == Document.uploaded_by_user_id)
        .filter(Document.patient_id == patient_id, Document.clinic_id == clinic_id)
    )
    total = query.count()
    rows = query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit).all()
    return [to_public(document, name) for document, name in rows], total


def get_document(db: Session, document_id: uuid.UUID, clinic_id: uuid.UUID) -> Document | None:
    return db.query(Document).filter(Document.id == document_id, Document.clinic_id == clinic_id).first()


def persist_document(
    db: Session,
    storage: LocalDocumentStorage,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    patient_user_id: uuid.UUID,
    user: User,
    title: str,
    filename: str,
    content_type: str,
    size: int,
    source: BinaryReader,
) -> Document:
    """Store the file, its metadata and the patient's notification atomically.

    Documents are append-only: there is no delete path. The patient is notified
    with generic text and a deep link (target) to the new document.
    """
    key = storage.new_key()
    storage.save(key, source)
    document = Document(
        clinic_id=clinic_id,
        patient_id=patient_id,
        uploaded_by_user_id=user.id,
        title=title,
        original_filename=filename,
        storage_key=key,
        content_type=content_type,
        file_size=size,
    )
    try:
        db.add(document)
        # The notification's composite foreign key needs the document row first.
        db.flush()
        db.add(
            Notification(
                clinic_id=clinic_id,
                user_id=patient_user_id,
                title=NEW_DOCUMENT_NOTIFICATION_TITLE,
                message=NEW_DOCUMENT_NOTIFICATION_MESSAGE,
                target_type="document",
                target_id=document.id,
            )
        )
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return document
