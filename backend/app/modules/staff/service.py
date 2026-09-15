from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Staff, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest


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
