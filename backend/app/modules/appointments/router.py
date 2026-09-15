from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic_id, get_current_user, require_roles
from app.models import User, UserRole
from app.modules.appointments.schemas import AppointmentCreateRequest, AppointmentPublic
from app.modules.appointments.service import create_appointment, list_appointments_for_user

router = APIRouter()


@router.post(
    "",
    response_model=AppointmentPublic,
    status_code=201,
    dependencies=[],
)
def create(
    payload: AppointmentCreateRequest,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _staff_user: User = Depends(require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)),
):
    return create_appointment(db, clinic_id, payload)


@router.get("", response_model=list[AppointmentPublic])
def list_mine(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Patients get their own appointments; staff/clinic_admin get every
    appointment in their own clinic. Scoping happens entirely server-side
    based on the authenticated session — see service.list_appointments_for_user.
    """
    return list_appointments_for_user(db, user)
