from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import set_session_cookie
from app.modules.patients.schemas import PatientPublic, PatientRegisterRequest
from app.modules.patients.service import register_patient

router = APIRouter()


@router.post("/register", response_model=PatientPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def register(request: Request, payload: PatientRegisterRequest, response: Response, db: Session = Depends(get_db)):
    patient, user = register_patient(db, payload)
    set_session_cookie(response, user)  # auto-login after successful registration
    return PatientPublic(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=user.full_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
    )
