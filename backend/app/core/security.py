"""
Security primitives: password hashing, JWT issuing/verification, and
FastAPI dependencies that enforce authentication + tenant (clinic) scoping.

Design decisions (do not change without discussion):
- Passwords hashed with Argon2id (via passlib's argon2 backend).
- Sessions are httpOnly cookies carrying a JWT, NOT localStorage.
- Each JWT embeds a `token_epoch` matching the user's current epoch in DB.
  Bumping the user's epoch (e.g. on password change / forced logout)
  instantly invalidates all previously issued tokens without needing
  a token blocklist.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, Response, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User, UserRole

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "clinic_id": str(user.clinic_id) if user.clinic_id else None,
        "role": user.role.value,
        "epoch": user.token_epoch,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        )


def set_session_cookie(response: Response, user: User) -> None:
    token = create_access_token(user)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.COOKIE_NAME, path="/")


def get_current_user(
    session_token: Optional[str] = Cookie(default=None, alias=settings.COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolves the authenticated user from the httpOnly session cookie.
    Rejects the request if the token is missing, invalid, expired,
    stale (epoch mismatch -> forced logout happened), or the user is inactive.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
        )

    payload = decode_access_token(session_token)
    user = db.get(User, payload.get("sub"))

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilizador inválido.",
        )

    if user.token_epoch != payload.get("epoch"):
        # Password changed / admin forced logout / token was revoked.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Inicie sessão novamente.",
        )

    return user


def require_roles(*allowed_roles: UserRole):
    """
    Dependency factory for endpoint-level authorization.
    Usage: Depends(require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN))
    """

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem permissões para aceder a este recurso.",
            )
        return user

    return _checker


def get_current_clinic_id(user: User = Depends(get_current_user)) -> str:
    """
    Every tenant-scoped query/endpoint MUST depend on this (directly or
    indirectly) and filter by it. Never trust a clinic_id coming from the
    request path/body/query params for authorization decisions.
    """
    if user.clinic_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilizador não está associado a nenhuma clínica.",
        )
    return str(user.clinic_id)
