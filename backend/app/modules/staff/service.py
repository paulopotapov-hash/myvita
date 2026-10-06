import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import Staff, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest
from app.modules.users import service as users_service


def create_staff_member(db: Session, clinic_id: str, payload: StaffCreateRequest) -> Staff:
    if db.query(User).filter(User.email_matches(payload.email)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe uma conta com este email.",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.STAFF,
        clinic_id=clinic_id,
        must_change_password=payload.require_password_change,
    )
    db.add(user)
    db.flush()

    staff = Staff(
        user_id=user.id,
        clinic_id=clinic_id,
        staff_role=payload.staff_role,
        specialty=payload.specialty,
        license_number=payload.license_number,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def deactivate_staff_member(db: Session, staff_id: uuid.UUID, clinic_id: str, actor: User) -> Staff:
    staff = (
        db.query(Staff)
        .options(selectinload(Staff.user))
        .filter(Staff.id == staff_id, Staff.clinic_id == clinic_id)
        .first()
    )
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado.")
    # Shared lifecycle rules: revoke sessions and outstanding reset links.
    users_service.deactivate(db, staff.user, actor)
    db.refresh(staff)
    return staff
