import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, Notification, User
from app.modules.notifications.schemas import NotificationPublic
from app.modules.notifications.service import list_notifications, mark_notification_read

router = APIRouter()


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
    record_audit_event(
        action=AuditAction.NOTIFICATION_READ,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="notification",
        resource_id=notification.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return notification
