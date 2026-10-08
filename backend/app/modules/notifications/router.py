import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, Notification, User
from app.modules.notifications.schemas import NotificationPublic
from app.modules.notifications.service import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
)

router = APIRouter()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    return {"count": unread_notification_count(db, user)}


@router.post("/read-all")
def mark_all_read(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    updated_count = mark_all_notifications_read(db, user)
    audit_request(
        request,
        action=AuditAction.NOTIFICATION_READ,
        actor=user,
        resource_type="notification",
        metadata={"operation": "read_all", "updated_count": updated_count},
    )
    return {"updated_count": updated_count}


@router.get("", response_model=list[NotificationPublic])
def list_mine(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Notification]:
    notifications, total = list_notifications(db, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    return notifications


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_read(
    notification_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Notification:
    notification = mark_notification_read(db, notification_id, user)
    audit_request(
        request,
        action=AuditAction.NOTIFICATION_READ,
        actor=user,
        resource_type="notification",
        resource_id=notification.id,
    )
    return notification
