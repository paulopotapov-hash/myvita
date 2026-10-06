import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, ClinicalDocument, ClinicalDocumentVersion, Staff, User
from app.modules.documents.schemas import DocumentNoteCreate, DocumentPublic, DocumentVersionPublic
from app.modules.documents.service import (
    create_note,
    current_patient_id,
    get_document,
    get_version,
    list_documents,
    read_file,
    update_file,
    update_note,
    upload_file,
)

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, document_id: uuid.UUID) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="document",
        resource_id=document_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _version_public(
    db: Session, version: ClinicalDocumentVersion, current_version: int
) -> DocumentVersionPublic:
    author = db.query(Staff).filter(Staff.id == version.author_staff_id).first()
    return DocumentVersionPublic(
        id=version.id,
        document_id=version.document_id,
        author_name=author.user.full_name if author else "Profissional",
        version=version.version,
        content=version.content,
        original_filename=version.original_filename,
        media_type=version.media_type,
        file_size=version.file_size,
        created_at=version.created_at,
        is_current=version.version == current_version,
    )


def _document_public(document: ClinicalDocument) -> DocumentPublic:
    current = next(
        (version for version in document.versions if version.version == document.current_version), None
    )
    return DocumentPublic(
        id=document.id,
        clinic_id=document.clinic_id,
        patient_id=document.patient_id,
        kind=document.kind,
        title=document.title,
        current_version=document.current_version,
        created_at=document.created_at,
        updated_at=document.updated_at,
        current_content=current.content if current else None,
        current_author=current.author_staff.user.full_name if current else None,
    )


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentPublic]:
    with audit_denials(request, user, "document", patient_id):
        documents = list_documents(db, patient_id, user)
    _audit(request, user, AuditAction.DOCUMENT_VIEWED, patient_id)
    return [_document_public(document) for document in documents]


@router.get("/documents/mine", response_model=list[DocumentPublic])
def list_mine(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DocumentPublic]:
    with audit_denials(request, user, "document", user.id):
        patient_id = current_patient_id(db, user)
        documents = list_documents(db, patient_id, user)
    _audit(request, user, AuditAction.DOCUMENT_VIEWED, patient_id)
    return [_document_public(document) for document in documents]


@router.post("/patients/{patient_id}/documents/notes", response_model=DocumentPublic, status_code=201)
def create_note_endpoint(
    patient_id: uuid.UUID,
    payload: DocumentNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    with audit_denials(request, user, "document", patient_id):
        document = create_note(db, patient_id, payload, user)
    _audit(request, user, AuditAction.DOCUMENT_CREATED, document.id)
    return _document_public(document)


@router.post("/patients/{patient_id}/documents/files", response_model=DocumentPublic, status_code=201)
def upload_file_endpoint(
    patient_id: uuid.UUID,
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    with audit_denials(request, user, "document", patient_id):
        document = upload_file(db, patient_id, title, file, user)
    _audit(request, user, AuditAction.DOCUMENT_CREATED, document.id)
    return _document_public(document)


@router.get("/documents/{document_id}", response_model=DocumentPublic)
def detail(
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    with audit_denials(request, user, "document", document_id):
        document = get_document(db, document_id, user)
    _audit(request, user, AuditAction.DOCUMENT_VIEWED, document.id)
    return _document_public(document)


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionPublic])
def history(
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentVersionPublic]:
    with audit_denials(request, user, "document", document_id):
        document = get_document(db, document_id, user)
    _audit(request, user, AuditAction.DOCUMENT_VIEWED, document.id)
    return [_version_public(db, item, document.current_version) for item in document.versions]


@router.get("/documents/{document_id}/versions/{version_number}", response_model=DocumentVersionPublic)
def version_detail(
    document_id: uuid.UUID,
    version_number: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentVersionPublic:
    with audit_denials(request, user, "document", document_id):
        document, version = get_version(db, document_id, version_number, user)
    _audit(request, user, AuditAction.DOCUMENT_VIEWED, document.id)
    return _version_public(db, version, document.current_version)


@router.patch("/documents/{document_id}/notes", response_model=DocumentPublic)
def update_note_endpoint(
    document_id: uuid.UUID,
    payload: DocumentNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    with audit_denials(request, user, "document", document_id):
        document = update_note(db, document_id, payload, user)
    _audit(request, user, AuditAction.DOCUMENT_UPDATED, document.id)
    return _document_public(document)


@router.post("/documents/{document_id}/files/versions", response_model=DocumentPublic)
def update_file_endpoint(
    document_id: uuid.UUID,
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    with audit_denials(request, user, "document", document_id):
        document = update_file(db, document_id, title, file, user)
    _audit(request, user, AuditAction.DOCUMENT_UPDATED, document.id)
    return _document_public(document)


@router.get("/documents/{document_id}/download")
def download_current(
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    return _download(document_id, None, request, db, user)


@router.get("/documents/{document_id}/versions/{version_number}/download")
def download_version(
    document_id: uuid.UUID,
    version_number: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    return _download(document_id, version_number, request, db, user)


def _download(
    document_id: uuid.UUID,
    version_number: int | None,
    request: Request,
    db: Session,
    user: User,
) -> StreamingResponse:
    with audit_denials(request, user, "document", document_id):
        version, payload = read_file(db, document_id, version_number, user)
    _audit(request, user, AuditAction.DOCUMENT_DOWNLOADED, document_id)
    filename = version.original_filename or "document.pdf"
    safe_ascii_name = "".join(
        char if 32 <= ord(char) < 127 and char not in {'"', "\\"} else "_" for char in filename
    )
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
