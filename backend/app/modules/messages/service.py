"""
Patient <-> clinical staff messaging (one thread per patient/professional pair).

Access rule, applied to every list, read and write:
- the conversation belongs to the caller's clinic, and
- the caller is its patient, or its professional **with a current, active
  ClinicalCareAssignment for that patient** and the messaging permission.
A professional whose assignment has ended gets the same 404 as for an unknown
conversation, so IDs can't be probed. Clinic admins and non-clinical staff are
never participants.

A thread is read-only for the patient when its professional has no active
assignment (or is deactivated): the patient keeps the history but the backend
rejects replies, so a patient message never lands in a thread nobody can read.

Only clinical staff with the messaging permission and an active assignment can
start a conversation; patients only reply in threads opened by staff.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, false, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.clinical_access import ClinicalAction, clinical_access, has_role_action, staff_profile
from app.models import (
    ClinicalCareAssignment,
    Conversation,
    Message,
    Notification,
    Patient,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.messages.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationPublic,
    MessagePublic,
)

_NOT_FOUND = "Conversa não encontrada."
INACTIVE_CONVERSATION = "Esta conversa já não está activa. Para continuar, contacte a clínica."
_PATIENTS_CANNOT_START = "Os pacientes não podem iniciar conversas."
_NO_MESSAGING = "Sem permissões para mensagens."

# Roles whose professional can still answer a thread (doctor/nurse today).
_REPLY_ROLES = tuple(role for role in StaffRole if has_role_action(role, ClinicalAction.REPLY_CONVERSATIONS))

# Deliberately generic: notifications may be seen on shared screens and are
# stored outside the conversation's access rules, so no message content or
# sender name goes into them.
NEW_MESSAGE_NOTIFICATION_TITLE = "Nova mensagem"
NEW_MESSAGE_NOTIFICATION_MESSAGE = "Recebeu uma nova mensagem. Abra as mensagens para a ler."


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _caller_side(db: Session, user: User) -> str | None:
    """'patient', 'staff' (clinical staff with the messaging permission) or None."""
    if user.role == UserRole.PATIENT:
        return "patient"
    staff = staff_profile(db, user)
    if staff is not None and has_role_action(staff.staff_role, ClinicalAction.VIEW_CONVERSATIONS):
        return "staff"
    return None


def _summary_query(db: Session, user: User) -> Any:
    """Conversations visible to the user, with names, unread count and reply state, in one query."""
    patient_user = aliased(User)
    staff_user = aliased(User)
    side = _caller_side(db, user)
    # The conversation's professional is currently on the patient's care team.
    assignment_active = (
        select(ClinicalCareAssignment.id)
        .where(
            ClinicalCareAssignment.clinic_id == Conversation.clinic_id,
            ClinicalCareAssignment.patient_id == Conversation.patient_id,
            ClinicalCareAssignment.staff_id == Conversation.staff_id,
            ClinicalCareAssignment.active.is_(True),
        )
        .correlate(Conversation)
        .exists()
    )
    can_reply = and_(assignment_active, staff_user.is_active.is_(True), Staff.staff_role.in_(_REPLY_ROLES))
    unread = (
        select(func.count(Message.id))
        .where(
            Message.conversation_id == Conversation.id,
            Message.sender_user_id != user.id,
            Message.read_at.is_(None),
        )
        .correlate(Conversation)
        .scalar_subquery()
    )
    query = (
        db.query(
            Conversation,
            patient_user.full_name.label("patient_name"),
            staff_user.full_name.label("staff_name"),
            unread.label("unread_count"),
            can_reply.label("can_reply"),
        )
        .join(Patient, Patient.id == Conversation.patient_id)
        .join(patient_user, patient_user.id == Patient.user_id)
        .join(Staff, Staff.id == Conversation.staff_id)
        .join(staff_user, staff_user.id == Staff.user_id)
        .filter(Conversation.clinic_id == user.clinic_id)
    )
    if side == "patient":
        # The patient always keeps their history; `can_reply` makes ended threads read-only.
        return query.filter(Patient.user_id == user.id)
    if side == "staff":
        # Participation alone is not enough: the assignment must be current (M1).
        return query.filter(Staff.user_id == user.id, assignment_active)
    return query.filter(false())


def _to_public(row: Any) -> ConversationPublic:
    conversation: Conversation = row[0]
    return ConversationPublic(
        id=conversation.id,
        clinic_id=conversation.clinic_id,
        patient_id=conversation.patient_id,
        staff_id=conversation.staff_id,
        patient_name=row.patient_name,
        staff_name=row.staff_name,
        unread_count=row.unread_count,
        can_reply=bool(row.can_reply),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _visible_row(db: Session, conversation_id: uuid.UUID, user: User) -> Any:
    row = _summary_query(db, user).filter(Conversation.id == conversation_id).first()
    if row is None:
        raise _not_found()
    return row


def _summary(db: Session, conversation_id: uuid.UUID, user: User) -> ConversationPublic:
    return _to_public(_visible_row(db, conversation_id, user))


def get_conversation_for_user(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    """The conversation when visible to the caller under the access rule above, else 404."""
    conversation: Conversation = _visible_row(db, conversation_id, user)[0]
    return conversation


def _resolve_participants(
    db: Session, payload: ConversationCreateRequest, user: User
) -> tuple[Patient, Staff]:
    """Only clinical staff open threads (M4), with the messaging permission AND an
    active care assignment to that patient (M3), via the central policy."""
    if user.role == UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_PATIENTS_CANNOT_START)
    patient = clinical_access(db, payload.patient_id, user, ClinicalAction.CREATE_CONVERSATIONS)
    staff = staff_profile(db, user)
    if staff is None:  # unreachable after clinical_access; keeps the type narrow
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NO_MESSAGING)
    return patient, staff


def create_conversation(
    db: Session, payload: ConversationCreateRequest, user: User
) -> tuple[ConversationPublic, bool]:
    """Returns (conversation, created). An existing pair is returned, not duplicated."""
    patient, staff = _resolve_participants(db, payload, user)
    existing = (
        db.query(Conversation)
        .filter(Conversation.patient_id == patient.id, Conversation.staff_id == staff.id)
        .first()
    )
    if existing is not None:
        return _summary(db, existing.id, user), False
    conversation = Conversation(clinic_id=user.clinic_id, patient_id=patient.id, staff_id=staff.id)
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent create of the same pair: the unique constraint won.
        db.rollback()
        existing = (
            db.query(Conversation)
            .filter(Conversation.patient_id == patient.id, Conversation.staff_id == staff.id)
            .one()
        )
        return _summary(db, existing.id, user), False
    return _summary(db, conversation.id, user), True


def list_conversations(
    db: Session, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[ConversationPublic], int]:
    if _caller_side(db, user) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NO_MESSAGING)
    query = _summary_query(db, user)
    total = query.count()
    rows = (
        query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_public(row) for row in rows], total


def get_conversation_detail(
    db: Session, conversation_id: uuid.UUID, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[ConversationDetail, int]:
    summary = _summary(db, conversation_id, user)
    query = db.query(Message).filter(
        Message.conversation_id == summary.id, Message.clinic_id == user.clinic_id
    )
    total = query.count()
    messages = query.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit).all()
    detail = ConversationDetail(
        **summary.model_dump(),
        messages=[MessagePublic.model_validate(message) for message in messages],
    )
    return detail, total


def send_message(db: Session, conversation_id: uuid.UUID, body: str, user: User) -> Message:
    row = _visible_row(db, conversation_id, user)
    conversation: Conversation = row[0]
    if not row.can_reply:
        # M2: enforced here, not only hidden in the UI. Nobody could read the reply.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_CONVERSATION)
    patient = db.get(Patient, conversation.patient_id)
    staff = db.get(Staff, conversation.staff_id)
    if patient is None or staff is None:
        raise _not_found()
    recipient_user_id = staff.user_id if patient.user_id == user.id else patient.user_id

    message = Message(
        conversation_id=conversation.id,
        clinic_id=conversation.clinic_id,
        sender_user_id=user.id,
        body=body,
    )
    db.add(message)
    # now() is the transaction timestamp, so this equals message.created_at.
    conversation.updated_at = func.now()
    db.add(
        Notification(
            clinic_id=conversation.clinic_id,
            user_id=recipient_user_id,
            title=NEW_MESSAGE_NOTIFICATION_TITLE,
            message=NEW_MESSAGE_NOTIFICATION_MESSAGE,
            # Deep link to the specific conversation (M6); access is re-checked on open.
            target_type="conversation",
            conversation_target_id=conversation.id,
        )
    )
    # Message, activity timestamp and notification commit together or not at all.
    db.commit()
    db.refresh(message)
    return message


def mark_conversation_read(db: Session, conversation_id: uuid.UUID, user: User) -> int:
    """Marks the caller's incoming unread messages as read. Never touches messages the caller sent."""
    conversation = get_conversation_for_user(db, conversation_id, user)
    updated = db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.clinic_id == user.clinic_id,
            Message.sender_user_id != user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
        .returning(Message.id)
    ).all()
    db.commit()
    return len(updated)
