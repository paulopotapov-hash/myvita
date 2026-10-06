import logging
import uuid
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import mfa
from app.core.audit import client_ip, record_audit_event
from app.core.config import settings
from app.core.database import get_db
from app.core.privacy import email_fingerprint, mask_email
from app.core.rate_limit import (
    AUTHENTICATED_WRITE_RATE_LIMIT,
    LOGIN_RATE_LIMIT,
    PASSWORD_RESET_RATE_LIMIT,
    limiter,
)
from app.core.security import (
    clear_session_cookie,
    get_current_user,
    get_current_user_allow_pending,
    hash_password,
    mfa_enabled_for,
    mfa_required_for,
    pending_account_action,
    set_session_cookie,
    verify_password,
)
from app.models import AuditAction, AuditResult, Patient, Staff, User
from app.modules.auth import mfa_service, password_reset
from app.modules.auth.schemas import (
    GenericMessage,
    LoginRequest,
    MfaChallengeResponse,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaRecoveryCodesResponse,
    MfaSetupResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    UserPublic,
)
from app.modules.auth.service import authenticate

logger = logging.getLogger("myvita.auth")

router = APIRouter()

MFA_CHALLENGE_COOKIE = "myvita_mfa_challenge"
MFA_CHALLENGE_PATH = "/api/v1/auth/mfa"


def _audit(
    request: Request,
    action: AuditAction,
    *,
    user: User | None = None,
    result: AuditResult = AuditResult.SUCCESS,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_audit_event(
        action=action,
        result=result,
        clinic_id=user.clinic_id if user else None,
        actor_user_id=user.id if user else None,
        actor_email=user.email if user else None,
        resource_type="user" if resource_id else None,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata=metadata,
    )


def _public_user(db: Session, user: User, *, mfa_verified: bool = False) -> UserPublic:
    staff = db.query(Staff).filter(Staff.user_id == user.id).first()
    patient = db.query(Patient).filter(Patient.user_id == user.id).first()
    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        clinic_id=user.clinic_id,
        staff_role=staff.staff_role if staff else None,
        patient_id=patient.id if patient else None,
        must_change_password=user.must_change_password,
        mfa_enabled=mfa_enabled_for(db, user),
        mfa_required=mfa_required_for(user),
        pending_action=pending_account_action(db, user, session_mfa_verified=mfa_verified),
    )


def _clear_mfa_challenge(response: Response) -> None:
    response.delete_cookie(key=MFA_CHALLENGE_COOKIE, path=MFA_CHALLENGE_PATH)


# ---------------------------------------------------------------------------
# Login / logout / session
# ---------------------------------------------------------------------------


@router.post("/login", response_model=UserPublic | MfaChallengeResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
def login(
    request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> UserPublic | MfaChallengeResponse:
    user = authenticate(
        db,
        payload.email,
        payload.password,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if mfa_enabled_for(db, user):
        # No session yet: only a short-lived, path-scoped challenge that the
        # /mfa/verify endpoint exchanges for a session.
        response.set_cookie(
            key=MFA_CHALLENGE_COOKIE,
            value=mfa.create_challenge_token(user.id, user.token_epoch),
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            max_age=mfa.CHALLENGE_TTL_SECONDS,
            path=MFA_CHALLENGE_PATH,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        _audit(request, AuditAction.LOGIN_MFA_CHALLENGE, user=user)
        return MfaChallengeResponse()

    set_session_cookie(response, user, mfa_verified=False)
    logger.info("Login bem-sucedido: user_id=%s", user.id)
    _audit(request, AuditAction.LOGIN_SUCCESS, user=user, metadata={"mfa": False})
    return _public_user(db, user)


@router.post("/mfa/verify", response_model=UserPublic)
@limiter.limit(LOGIN_RATE_LIMIT)
def verify_mfa(
    request: Request,
    payload: MfaCodeRequest,
    response: Response,
    challenge: str | None = Cookie(default=None, alias=MFA_CHALLENGE_COOKIE),
    db: Session = Depends(get_db),
) -> UserPublic:
    expired = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A verificação expirou. Inicie sessão novamente.",
    )
    claims = mfa.decode_challenge_token(challenge) if challenge else None
    if claims is None:
        raise expired
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active or user.token_epoch != claims["epoch"]:
        raise expired
    try:
        result = mfa_service.verify(db, user, payload.code)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            _audit(request, AuditAction.MFA_FAILURE, user=user, result=AuditResult.FAILURE)
        raise
    _clear_mfa_challenge(response)
    set_session_cookie(response, user, mfa_verified=True)
    if result.method == "recovery_code":
        _audit(
            request,
            AuditAction.MFA_RECOVERY_CODE_USED,
            user=user,
            metadata={"recovery_codes_remaining": result.recovery_codes_remaining},
        )
    _audit(request, AuditAction.LOGIN_SUCCESS, user=user, metadata={"mfa": True, "method": result.method})
    return _public_user(db, user, mfa_verified=True)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_pending),
) -> None:
    # Bump token_epoch, not just clear the cookie: this invalidates the
    # token immediately even if it was copied/stolen before logout.
    user.token_epoch += 1
    db.commit()
    logger.info("Logout: user_id=%s", user.id)
    _audit(request, AuditAction.LOGOUT, user=user)
    clear_session_cookie(response)


@router.get("/me", response_model=UserPublic)
def me(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user_allow_pending)
) -> UserPublic:
    return _public_user(db, user, mfa_verified=request.state.session_mfa_verified)


@router.post("/change-password", status_code=204)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_pending),
) -> None:
    session_mfa_verified: bool = request.state.session_mfa_verified
    if mfa_enabled_for(db, user) and not session_mfa_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Valide primeiro o segundo fator.")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Palavra-passe atual incorreta.")
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A nova palavra-passe deve ser diferente.",
        )
    was_forced = user.must_change_password
    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    user.token_epoch += 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user, mfa_verified=session_mfa_verified)
    _audit(request, AuditAction.PASSWORD_CHANGE, user=user, metadata={"forced": was_forced})


# ---------------------------------------------------------------------------
# MFA enrolment / management
# ---------------------------------------------------------------------------


def _reject_unverified_session(request: Request, db: Session, user: User) -> None:
    if mfa_enabled_for(db, user) and not request.state.session_mfa_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Valide primeiro o segundo fator.")


@router.post("/mfa/setup", response_model=MfaSetupResponse)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def mfa_setup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_pending),
) -> MfaSetupResponse:
    _reject_unverified_session(request, db, user)
    setup = mfa_service.start_setup(db, user)
    # The seed is returned exactly once, over this response only; it is
    # never logged or audited.
    return MfaSetupResponse(secret=setup.secret, otpauth_uri=setup.otpauth_uri)


@router.post("/mfa/enable", response_model=MfaRecoveryCodesResponse)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def mfa_enable(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_pending),
) -> MfaRecoveryCodesResponse:
    try:
        codes = mfa_service.enable(db, user, payload.code)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            _audit(request, AuditAction.MFA_FAILURE, user=user, result=AuditResult.FAILURE, metadata={"stage": "enable"})
        raise
    set_session_cookie(response, user, mfa_verified=True)
    _audit(request, AuditAction.MFA_ENABLED, user=user, resource_id=user.id)
    return MfaRecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/disable", status_code=204)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        mfa_service.disable(db, user, current_password=payload.current_password, code=payload.code)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            _audit(request, AuditAction.MFA_FAILURE, user=user, result=AuditResult.FAILURE, metadata={"stage": "disable"})
        raise
    set_session_cookie(response, user, mfa_verified=False)
    _audit(request, AuditAction.MFA_DISABLED, user=user, resource_id=user.id)


@router.post("/mfa/recovery-codes", response_model=MfaRecoveryCodesResponse)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def mfa_regenerate_recovery_codes(
    payload: MfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MfaRecoveryCodesResponse:
    try:
        codes = mfa_service.regenerate_recovery_codes(db, user, payload.code)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            _audit(request, AuditAction.MFA_FAILURE, user=user, result=AuditResult.FAILURE, metadata={"stage": "regenerate"})
        raise
    _audit(request, AuditAction.MFA_RECOVERY_CODES_REGENERATED, user=user, resource_id=user.id)
    return MfaRecoveryCodesResponse(recovery_codes=codes)


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


@router.post("/password-reset/confirm", status_code=204)
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    user = password_reset.complete(db, payload.token, payload.new_password)
    _audit(request, AuditAction.PASSWORD_RESET_COMPLETED, user=user, resource_id=user.id)


@router.post("/password-reset/request", status_code=202, response_model=GenericMessage)
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> GenericMessage:
    """
    Self-service entry point. No delivery channel (e-mail/SMS) is approved
    yet, so this never issues a token: it records the request for the
    clinic's audit trail and always answers the same way, whether or not the
    address has an account, so it cannot be used to enumerate users.
    """
    account = db.query(User).filter(User.email_matches(payload.email)).first()
    target = account if account is not None and account.is_active else None
    # The requester is anonymous: there is never an actor. A matching active
    # account is recorded as the *resource* (and its clinic, so the clinic
    # admin sees the request); the typed address only masked/fingerprinted.
    record_audit_event(
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        result=AuditResult.SUCCESS,
        clinic_id=target.clinic_id if target else None,
        resource_type="user" if target else None,
        resource_id=target.id if target else None,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "delivery": "disabled",
            "account_found": target is not None,
            "email_masked": mask_email(payload.email),
            "email_fingerprint": email_fingerprint(payload.email),
        },
    )
    return GenericMessage(
        detail="Se existir uma conta com este email, contacte o administrador da sua clínica para obter uma ligação de redefinição."
    )
