import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.models import (
    ClinicalDocument,
    ClinicalDocumentVersion,
    DocumentKind,
    Notification,
    Patient,
    User,
    UserRole,
)
from app.modules.documents.schemas import DocumentNoteCreate
from app.modules.documents.storage import document_storage


def _authorized_patient(db: Session, patient_id: uuid.UUID, user: User, *, edit: bool = False) -> Patient:
    action = ClinicalAction.EDIT_DOCUMENTS if edit else ClinicalAction.VIEW_DOCUMENTS
    return clinical_access(db, patient_id, user, action)


def list_documents(db: Session, patient_id: uuid.UUID, user: User) -> list[ClinicalDocument]:
    patient = _authorized_patient(db, patient_id, user)
    return (
        db.query(ClinicalDocument)
        .options(joinedload(ClinicalDocument.versions))
        .filter(ClinicalDocument.patient_id == patient.id, ClinicalDocument.clinic_id == patient.clinic_id)
        .order_by(ClinicalDocument.updated_at.desc(), ClinicalDocument.id)
        .all()
    )


def get_document(
    db: Session, document_id: uuid.UUID, user: User, *, for_update: bool = False
) -> ClinicalDocument:
    query = db.query(ClinicalDocument).filter(
        ClinicalDocument.id == document_id, ClinicalDocument.clinic_id == user.clinic_id
    )
    if for_update:
        query = query.with_for_update()
    options = selectinload(ClinicalDocument.versions) if for_update else joinedload(ClinicalDocument.versions)
    document = query.options(options).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    _authorized_patient(db, document.patient_id, user)
    return document


def get_version(
    db: Session, document_id: uuid.UUID, version_number: int, user: User
) -> tuple[ClinicalDocument, ClinicalDocumentVersion]:
    document = get_document(db, document_id, user)
    version = next((row for row in document.versions if row.version == version_number), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    return document, version


def _notify_patient(db: Session, document: ClinicalDocument, author_name: str, *, updated: bool) -> None:
    patient = db.query(Patient).filter(Patient.id == document.patient_id).one()
    db.add(
        Notification(
            clinic_id=document.clinic_id,
            user_id=patient.user_id,
            title="Documento atualizado" if updated else "Novo documento",
            message=f"{author_name} {'atualizou' if updated else 'adicionou'} “{document.title}”.",
            target_type="document",
            target_id=document.id,
        )
    )


def _new_document(
    db: Session, patient: Patient, staff_id: uuid.UUID, kind: DocumentKind, title: str
) -> ClinicalDocument:
    document = ClinicalDocument(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        author_staff_id=staff_id,
        kind=kind,
        title=title,
        current_version=1,
    )
    db.add(document)
    db.flush()
    return document


def create_note(
    db: Session, patient_id: uuid.UUID, payload: DocumentNoteCreate, user: User
) -> ClinicalDocument:
    patient = _authorized_patient(db, patient_id, user, edit=True)
    staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_DOCUMENTS)
    document = _new_document(db, patient, staff.id, DocumentKind.NOTE, payload.title)
    db.add(
        ClinicalDocumentVersion(
            document_id=document.id,
            clinic_id=document.clinic_id,
            patient_id=document.patient_id,
            author_staff_id=staff.id,
            version=1,
            content=payload.content,
        )
    )
    _notify_patient(db, document, user.full_name, updated=False)
    db.commit()
    return get_document(db, document.id, user)


def upload_file(
    db: Session, patient_id: uuid.UUID, title: str, upload: UploadFile, user: User
) -> ClinicalDocument:
    patient = _authorized_patient(db, patient_id, user, edit=True)
    staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_DOCUMENTS)
    storage_key, checksum, size = document_storage.save_pdf(upload)
    try:
        title = title.strip()
        if not title or len(title) > 200:
            raise HTTPException(status_code=422, detail="Título inválido.")
        document = _new_document(db, patient, staff.id, DocumentKind.FILE, title.strip())
        db.add(
            ClinicalDocumentVersion(
                document_id=document.id,
                clinic_id=document.clinic_id,
                patient_id=document.patient_id,
                author_staff_id=staff.id,
                version=1,
                original_filename=(upload.filename or "document.pdf").strip(),
                media_type="application/pdf",
                file_size=size,
                checksum_sha256=checksum,
                storage_key=storage_key,
            )
        )
        _notify_patient(db, document, user.full_name, updated=False)
        db.commit()
    except Exception:
        db.rollback()
        document_storage.delete(storage_key)
        raise
    return get_document(db, document.id, user)


def update_note(
    db: Session, document_id: uuid.UUID, payload: DocumentNoteCreate, user: User
) -> ClinicalDocument:
    document = get_document(db, document_id, user, for_update=True)
    if document.kind != DocumentKind.NOTE:
        raise HTTPException(status_code=409, detail="Apenas notas podem ser editadas como texto.")
    _authorized_patient(db, document.patient_id, user, edit=True)
    staff = clinical_staff(db, user, document.patient_id, ClinicalAction.EDIT_DOCUMENTS)
    new_number = document.current_version + 1
    document.title = payload.title
    document.current_version = new_number
    document.updated_at = datetime.now(UTC)
    db.add(
        ClinicalDocumentVersion(
            document_id=document.id,
            clinic_id=document.clinic_id,
            patient_id=document.patient_id,
            author_staff_id=staff.id,
            version=new_number,
            content=payload.content,
        )
    )
    _notify_patient(db, document, user.full_name, updated=True)
    db.commit()
    return get_document(db, document.id, user)


def update_file(
    db: Session, document_id: uuid.UUID, title: str, upload: UploadFile, user: User
) -> ClinicalDocument:
    document = get_document(db, document_id, user, for_update=True)
    if document.kind != DocumentKind.FILE:
        raise HTTPException(status_code=409, detail="Apenas documentos de ficheiro aceitam novos ficheiros.")
    _authorized_patient(db, document.patient_id, user, edit=True)
    staff = clinical_staff(db, user, document.patient_id, ClinicalAction.EDIT_DOCUMENTS)
    title = title.strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=422, detail="Título inválido.")
    storage_key, checksum, size = document_storage.save_pdf(upload)
    try:
        new_number = document.current_version + 1
        document.title = title
        document.current_version = new_number
        document.updated_at = datetime.now(UTC)
        db.add(
            ClinicalDocumentVersion(
                document_id=document.id,
                clinic_id=document.clinic_id,
                patient_id=document.patient_id,
                author_staff_id=staff.id,
                version=new_number,
                original_filename=(upload.filename or "document.pdf").strip(),
                media_type="application/pdf",
                file_size=size,
                checksum_sha256=checksum,
                storage_key=storage_key,
            )
        )
        _notify_patient(db, document, user.full_name, updated=True)
        db.commit()
    except Exception:
        db.rollback()
        document_storage.delete(storage_key)
        raise
    return get_document(db, document.id, user)


def read_file(
    db: Session, document_id: uuid.UUID, version_number: int | None, user: User
) -> tuple[ClinicalDocumentVersion, bytes]:
    document = get_document(db, document_id, user)
    if document.kind != DocumentKind.FILE:
        raise HTTPException(status_code=409, detail="O documento não contém um ficheiro.")
    version_number = version_number or document.current_version
    _, version = get_version(db, document.id, version_number, user)
    if not version.storage_key:
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado.")
    return version, document_storage.read(version.storage_key)


def current_patient_id(db: Session, user: User) -> uuid.UUID:
    if user.role != UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas pacientes.")
    patient = (
        db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return patient.id
