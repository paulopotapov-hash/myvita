"""Internal notification creation; no public send endpoint."""
from sqlalchemy.orm import Session

from app.models import Notification, User


def create_notification(db: Session, recipient: User, title: str, message: str, kind: str) -> Notification:
    if recipient.clinic_id is None:
        raise ValueError("Recipient must belong to a clinic")
    item = Notification(
        clinic_id=recipient.clinic_id,
        recipient_user_id=recipient.id,
        title=title,
        message=message,
        kind=kind,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
