import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import Staff, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest, StaffRoleUpdateRequest


def create_staff_member(db: Session, clinic_id: str, payload: StaffCreateRequest) -> Staff:
    if db.query(User).filter(User.email == payload.email).first() is not None:
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


def deactivate_staff_member(
    db: Session, staff_id: uuid.UUID, clinic_id: str, actor_user_id: uuid.UUID
) -> Staff:
    staff = (
        db.query(Staff)
        .options(selectinload(Staff.user))
        .filter(Staff.id == staff_id, Staff.clinic_id == clinic_id)
        .first()
    )
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado.")
    if staff.user_id == actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não pode desativar a própria conta administrativa.",
        )
    if staff.user.is_active:
        staff.user.is_active = False
        staff.user.token_epoch += 1
        db.commit()
        db.refresh(staff)
    return staff


def activate_staff_member(db: Session, staff_id: uuid.UUID, clinic_id: str) -> Staff:
    staff = (
        db.query(Staff)
        .options(selectinload(Staff.user))
        .filter(Staff.id == staff_id, Staff.clinic_id == clinic_id)
        .first()
    )
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado.")
    if not staff.user.is_active:
        staff.user.is_active = True
        staff.user.token_epoch += 1
        db.commit()
        db.refresh(staff)
    return staff


def update_staff_role(
    db: Session, staff_id: uuid.UUID, clinic_id: str, payload: StaffRoleUpdateRequest
) -> Staff:
    staff = (
        db.query(Staff)
        .options(selectinload(Staff.user))
        .filter(Staff.id == staff_id, Staff.clinic_id == clinic_id)
        .first()
    )
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado.")
    if staff.staff_role != payload.staff_role or staff.specialty != payload.specialty:
        staff.staff_role = payload.staff_role
        staff.specialty = payload.specialty
        staff.user.token_epoch += 1
        db.commit()
        db.refresh(staff)
    return staff
