"""Private local document storage; callers authorize before reading by opaque key."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

MAX_FILE_BYTES = settings.DOCUMENT_MAX_FILE_BYTES


def _root() -> Path:
    root = Path(settings.DOCUMENT_STORAGE_DIR).expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def save_pdf(upload: UploadFile) -> tuple[str, str, int]:
    name = (upload.filename or "").strip()
    if (
        not name
        or len(name) > 255
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or any(ord(char) < 32 for char in name)
    ):
        raise HTTPException(status_code=422, detail="Nome de ficheiro inválido.")
    if Path(name).suffix.lower() != ".pdf" or (upload.content_type or "").lower() != "application/pdf":
        raise HTTPException(status_code=422, detail="Apenas ficheiros PDF são permitidos.")

    payload = upload.file.read(MAX_FILE_BYTES + 1)
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="O ficheiro excede o tamanho permitido.")
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="O conteúdo não corresponde a um PDF válido.")

    key = uuid.uuid4().hex
    root = _root()
    target = root / key
    if target.parent != root:
        raise HTTPException(status_code=422, detail="Referência de armazenamento inválida.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return key, hashlib.sha256(payload).hexdigest(), len(payload)


def read(key: str) -> bytes:
    if not key.isalnum() or len(key) != 32:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ficheiro não encontrado.")
    root = _root()
    target = (root / key).resolve()
    if target.parent != root or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ficheiro não encontrado.")
    return target.read_bytes()


def delete(key: str) -> None:
    if key.isalnum() and len(key) == 32:
        (_root() / key).unlink(missing_ok=True)


class DocumentStorage(Protocol):
    def save_pdf(self, upload: UploadFile) -> tuple[str, str, int]: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalDocumentStorage:
    """Filesystem implementation of the private document storage contract."""

    save_pdf = staticmethod(save_pdf)
    read = staticmethod(read)
    delete = staticmethod(delete)


document_storage: DocumentStorage = LocalDocumentStorage()
