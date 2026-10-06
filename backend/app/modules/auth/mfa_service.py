"""MFA enrolment and verification. See app/core/mfa.py for the primitives."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import mfa
from app.core.security import mfa_required_for, verify_password
from app.models import MfaRecoveryCode, User, UserMfa


@dataclass(frozen=True)
class MfaSetup:
    secret: str
    otpauth_uri: str


@dataclass(frozen=True)
class VerificationResult:
    method: str  # "totp" | "recovery_code"
    recovery_codes_remaining: int | None = None


_INVALID_CODE = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de verificação inválido.")


def _locked_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiadas tentativas falhadas. Tente novamente mais tarde.",
    )


def _mfa_row(db: Session, user: User, *, lock: bool = False) -> UserMfa | None:
    query = db.query(UserMfa).filter(UserMfa.user_id == user.id)
    if lock:
        query = query.with_for_update()
    return query.first()


def start_setup(db: Session, user: User) -> MfaSetup:
    row = _mfa_row(db, user, lock=True)
    if row is not None and row.enabled_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A autenticação de dois fatores já está ativa.")
    secret = mfa.generate_secret()
    ciphertext = mfa.encrypt_secret(secret, user.id)
    if row is None:
        db.add(UserMfa(user_id=user.id, secret_ciphertext=ciphertext))
    else:
        # Restarting setup replaces the pending seed; nothing was ever active.
        row.secret_ciphertext = ciphertext
        row.failed_attempts = 0
        row.locked_until = None
        row.last_used_step = None
    db.commit()
    return MfaSetup(secret=secret, otpauth_uri=mfa.provisioning_uri(secret, user.email))


def _ensure_not_locked(row: UserMfa) -> None:
    if row.locked_until is not None and row.locked_until > datetime.now(UTC):
        raise _locked_error()


def _register_failure(db: Session, row: UserMfa) -> None:
    row.failed_attempts += 1
    if row.failed_attempts >= mfa.MAX_FAILED_ATTEMPTS:
        row.locked_until = datetime.now(UTC) + timedelta(minutes=mfa.LOCKOUT_MINUTES)
        row.failed_attempts = 0
    db.commit()


def _replace_recovery_codes(db: Session, user: User) -> list[str]:
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete(synchronize_session=False)
    codes = mfa.generate_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=mfa.hash_recovery_code(code)))
    return codes


def _check_totp(row: UserMfa, user: User, code: str) -> int | None:
    secret = mfa.decrypt_secret(row.secret_ciphertext, user.id)
    return mfa.verify_totp(secret, code, last_used_step=row.last_used_step)


def enable(db: Session, user: User, code: str) -> list[str]:
    """Confirm the pending seed with a first code; returns one-time recovery codes."""
    row = _mfa_row(db, user, lock=True)
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inicie primeiro a configuração.")
    if row.enabled_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A autenticação de dois fatores já está ativa.")
    _ensure_not_locked(row)
    step = _check_totp(row, user, code)
    if step is None:
        _register_failure(db, row)
        raise _INVALID_CODE
    row.enabled_at = datetime.now(UTC)
    row.last_used_step = step
    row.failed_attempts = 0
    row.locked_until = None
    codes = _replace_recovery_codes(db, user)
    # Re-key the session: earlier sessions were established without MFA.
    user.token_epoch += 1
    db.commit()
    db.refresh(user)
    return codes


def verify(db: Session, user: User, code: str, *, allow_recovery_code: bool = True) -> VerificationResult:
    """Second-factor check for an enrolled user (login, disable, regenerate)."""
    row = _mfa_row(db, user, lock=True)
    if row is None or row.enabled_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Autenticação de dois fatores não configurada.")
    _ensure_not_locked(row)

    if allow_recovery_code and mfa.looks_like_recovery_code(code):
        recovery = (
            db.query(MfaRecoveryCode)
            .filter(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == mfa.hash_recovery_code(code),
                MfaRecoveryCode.used_at.is_(None),
            )
            .with_for_update()
            .first()
        )
        if recovery is None:
            _register_failure(db, row)
            raise _INVALID_CODE
        recovery.used_at = datetime.now(UTC)
        row.failed_attempts = 0
        db.commit()
        remaining = (
            db.query(MfaRecoveryCode)
            .filter(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
            .count()
        )
        return VerificationResult(method="recovery_code", recovery_codes_remaining=remaining)

    step = _check_totp(row, user, code)
    if step is None:
        _register_failure(db, row)
        raise _INVALID_CODE
    row.last_used_step = step
    row.failed_attempts = 0
    db.commit()
    return VerificationResult(method="totp")


def disable(db: Session, user: User, *, current_password: str, code: str) -> None:
    if mfa_required_for(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A autenticação de dois fatores é obrigatória para este perfil.",
        )
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Palavra-passe atual incorreta.")
    verify(db, user, code, allow_recovery_code=False)
    remove_enrolment(db, user)


def remove_enrolment(db: Session, user: User) -> None:
    """Delete seed and recovery codes and revoke every session (disable / admin reset)."""
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete(synchronize_session=False)
    db.query(UserMfa).filter(UserMfa.user_id == user.id).delete(synchronize_session=False)
    user.token_epoch += 1
    db.commit()
    db.refresh(user)


def regenerate_recovery_codes(db: Session, user: User, code: str) -> list[str]:
    verify(db, user, code, allow_recovery_code=False)
    codes = _replace_recovery_codes(db, user)
    db.commit()
    return codes
