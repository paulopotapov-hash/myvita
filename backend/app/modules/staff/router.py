from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic_id, require_roles
from app.models import User, UserRole
from app.modules.staff.schemas import StaffCreateRequest, StaffPublic
from app.modules.staff.service import create_staff_member

router = APIRouter()


@router.post("", response_model=StaffPublic, status_code=201)
def create(
    payload: StaffCreateRequest,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _admin: User = Depends(require_roles(UserRole.CLINIC_ADMIN)),
):
    staff = create_staff_member(db, clinic_id, payload)
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=payload.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
    )
