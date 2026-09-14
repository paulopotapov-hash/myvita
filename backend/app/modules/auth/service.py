from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()

    # Deliberately identical error for "no such user" and "wrong password":
    # a different message would let an attacker enumerate registered emails.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email ou palavra-passe incorretos.",
    )

    if user is None or not user.is_active:
        raise invalid_credentials

    if not verify_password(password, user.hashed_password):
        raise invalid_credentials

    return user
