import re
import tempfile
import uuid
from typing import BinaryIO
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, audit_request
from app.core.clinical_access import accessible_patient
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, Document, User
from app.modules.documents.schemas import DOCUMENT_TITLE_MAX_LENGTH, DocumentPublic
from app.modules.documents.service import (
    get_document,
    list_patient_documents,
    persist_document,
    to_public,
)
from app.modules.documents.storage import LocalDocumentStorage

router = APIRouter()
_ALLOWED = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}
_FILENAME = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,255}$")


def _storage() -> LocalDocumentStorage:
    return LocalDocumentStorage(settings.DOCUMENT_STORAGE_DIR)


def _clinic_id(user: User) -> uuid.UUID:
    if user.clinic_id is None:
        raise HTTPException(status_code=403, detail="Sem permissões clínicas.")
    return user.clinic_id


def _audit(request: Request, user: User, action: AuditAction, document: Document) -> None:
    audit_request(
        request,
        action=action,
        actor=user,
        resource_type="document",
        resource_id=document.id,
        metadata={"patient_id": document.patient_id},
    )


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentPublic]:
    with audit_denials(request, user, "document", patient_id):
        clinic_id = _clinic_id(user)
        accessible_patient(db, patient_id, user)
    documents, total = list_patient_documents(
        db, patient_id, clinic_id, offset=(page - 1) * page_size, limit=page_size
    )
    response.headers["X-Total-Count"] = str(total)
    # Parent A pattern: a list view is a clinical read, audited against the patient.
    audit_request(
        request,
        action=AuditAction.DOCUMENT_VIEWED,
        actor=user,
        resource_type="document",
        resource_id=patient_id,
        metadata={"patient_id": patient_id, "operation": "list", "count": len(documents)},
    )
    return documents


@router.post(
    "/patients/{patient_id}/documents",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
)
def upload(
    patient_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI multipart dependency
    title: str = Form(..., max_length=DOCUMENT_TITLE_MAX_LENGTH),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentPublic:
    # accessible_patient(write=True) enforces tenant, role, EDIT_DOCUMENTS and care assignment.
    with audit_denials(request, user, "document", patient_id):
        _clinic_id(user)
        patient = accessible_patient(db, patient_id, user, write=True)
    title = title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Indica um título para o documento.")
    filename = file.filename or ""
    if not _FILENAME.fullmatch(filename) or filename in {".", ".."}:
        raise HTTPException(status_code=422, detail="Nome de ficheiro inválido.")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    extension = f".{extension}"
    allowed = _ALLOWED.get(extension)
    if allowed is None or (file.content_type or "").lower() != allowed[0]:
        raise HTTPException(
            status_code=422, detail="Formato não suportado. Envia um PDF, PNG ou JPEG válido."
        )

    size = 0
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as buffer:
        while chunk := file.file.read(64 * 1024):
            size += len(chunk)
            if size > settings.DOCUMENT_MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="O ficheiro excede o tamanho máximo permitido.")
            buffer.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="O ficheiro está vazio.")
        buffer.seek(0)
        signature = buffer.read(16)
        if not allowed[1](signature):
            raise HTTPException(
                status_code=422, detail="O conteúdo do ficheiro não corresponde ao formato indicado."
            )
        buffer.seek(0)
        try:
            document = persist_document(
                db,
                _storage(),
                clinic_id=patient.clinic_id,
                patient_id=patient.id,
                patient_user_id=patient.user_id,
                user=user,
                title=title,
                filename=filename,
                content_type=allowed[0],
                size=size,
                source=buffer,
            )
        except OSError:
            raise HTTPException(status_code=503, detail="Não foi possível guardar o documento.") from None
    _audit(request, user, AuditAction.DOCUMENT_UPLOADED, document)
    return to_public(document, user.full_name)


@router.get(
    "/documents/{document_id}/download", responses={404: {"description": "Documento não encontrado."}}
)
def download(
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    with audit_denials(request, user, "document", document_id):
        document = get_document(db, document_id, _clinic_id(user))
        if document is None:
            raise HTTPException(status_code=404, detail="Documento não encontrado.")
        accessible_patient(db, document.patient_id, user)
    storage = _storage()
    try:
        stream: BinaryIO = storage.open(document.storage_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado.") from None
    except OSError:
        raise HTTPException(status_code=503, detail="Não foi possível abrir o documento.") from None
    _audit(request, user, AuditAction.DOCUMENT_DOWNLOADED, document)
    safe_name = quote(document.original_filename, safe="")
    return StreamingResponse(
        stream,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


# No delete route: clinical documents are append-only until a retention and
# deletion policy is legally validated. Corrections are made by uploading a new
# document (integration decision D3).
