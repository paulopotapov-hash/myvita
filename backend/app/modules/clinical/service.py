"""Internal notification creation; no public send endpoint."""

from sqlalchemy.orm import Session

from app.models import Notification, User


def create_notification(db: Session, recipient: User, title: str, message: str, kind: str) -> Notification:
    if recipient.clinic_id is None:
        raise ValueError("Recipient must belong to a clinic")
    title, message, kind = title.strip(), message.strip(), kind.strip()
    if not title or len(title) > 255:
        raise ValueError("Notification title must contain 1 to 255 characters")
    if not message or len(message) > 2_000:
        raise ValueError("Notification message must contain 1 to 2000 characters")
    if not kind or len(kind) > 50:
        raise ValueError("Notification kind must contain 1 to 50 characters")
    item = Notification(
        clinic_id=recipient.clinic_id,
        recipient_user_id=recipient.id,
        title=title,
        message=message,
        kind=kind,
    )
    db.add(item)
    db.flush()
    return item
