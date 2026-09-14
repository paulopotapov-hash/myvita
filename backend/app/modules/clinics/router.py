from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import set_session_cookie
from app.models import Clinic
from app.modules.clinics.schemas import ClinicOnboardingRequest, ClinicPublic, ClinicSummary
from app.modules.clinics.service import onboard_clinic

router = APIRouter()


@router.post("", response_model=ClinicPublic, status_code=201)
def create_clinic(payload: ClinicOnboardingRequest, response: Response, db: Session = Depends(get_db)):
    clinic, admin_user = onboard_clinic(db, payload)
    set_session_cookie(response, admin_user)  # auto-login the new admin
    return clinic


@router.get("", response_model=list[ClinicSummary])
def list_clinics(db: Session = Depends(get_db)):
    """
    Public, minimal clinic directory — just id + name — so a patient
    sign-up form can offer a clinic picker. No sensitive clinic data here.
    """
    return db.query(Clinic).order_by(Clinic.name).all()
