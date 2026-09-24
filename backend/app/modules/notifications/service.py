import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Notification, User


def list_notifications(
    db: Session, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[Notification], int]:
    query = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.clinic_id == user.clinic_id
    )
    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def mark_notification_read(db: Session, notification_id: uuid.UUID, user: User) -> Notification:
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.clinic_id == user.clinic_id,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada.")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)
    return notification
