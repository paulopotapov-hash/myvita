from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import clear_session_cookie, get_current_user, set_session_cookie
from app.models import User
from app.modules.auth.schemas import LoginRequest, UserPublic
from app.modules.auth.service import authenticate

router = APIRouter()


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, payload.email, payload.password)
    set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Bump token_epoch, not just clear the cookie: this invalidates the
    # token immediately even if it was copied/stolen before logout.
    user.token_epoch += 1
    db.commit()
    clear_session_cookie(response)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return user
