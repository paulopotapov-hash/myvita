import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import LOGIN_RATE_LIMIT, limiter
from app.core.security import clear_session_cookie, get_current_user, set_session_cookie
from app.models import AuditAction, AuditResult, Patient, Staff, User
from app.modules.auth.schemas import LoginRequest, UserPublic
from app.modules.auth.service import authenticate

logger = logging.getLogger("myvita.auth")

router = APIRouter()


@router.post("/login", response_model=UserPublic)
@limiter.limit(LOGIN_RATE_LIMIT)
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = authenticate(
        db,
        payload.email,
        payload.password,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    # Bump token_epoch, not just clear the cookie: this invalidates the
    # token immediately even if it was copied/stolen before logout.
    user.token_epoch += 1
    db.commit()
    logger.info("Logout: user_id=%s", user.id)
    record_audit_event(
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    clear_session_cookie(response)


def _public_user(db: Session, user: User) -> UserPublic:
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
    )


@router.get("/me", response_model=UserPublic)
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UserPublic:
    return _public_user(db, user)
