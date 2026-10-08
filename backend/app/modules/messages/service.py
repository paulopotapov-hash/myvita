"""
Patient <-> clinical staff messaging.

Access rule, applied to every read and write: a conversation is visible only
when it belongs to the caller's clinic AND the caller is its patient or its
staff member. Anything else is a 404 so IDs of other conversations can't be
probed. Clinic admins and non-clinical staff are never participants.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.clinical_access import CLINICAL_STAFF_ROLES, accessible_patient, clinical_staff
from app.models import Appointment, Conversation, Message, Notification, Patient, Staff, User, UserRole
from app.modules.messages.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationPublic,
    MessagePublic,
)

_NOT_FOUND = "Conversa não encontrada."

# Deliberately generic: notifications may be seen on shared screens and are
# stored outside the conversation's access rules, so no message content or
# sender name goes into them.
NEW_MESSAGE_NOTIFICATION_TITLE = "Nova mensagem"
NEW_MESSAGE_NOTIFICATION_MESSAGE = "Recebeu uma nova mensagem. Abra as mensagens para a ler."


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _summary_query(db: Session, user: User) -> Any:
    """Conversations the user participates in, with names and unread count, in one query."""
    patient_user = aliased(User)
    staff_user = aliased(User)
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
    return (
        db.query(
            Conversation,
            patient_user.full_name.label("patient_name"),
            staff_user.full_name.label("staff_name"),
            unread.label("unread_count"),
        )
        .join(Patient, Patient.id == Conversation.patient_id)
        .join(patient_user, patient_user.id == Patient.user_id)
        .join(Staff, Staff.id == Conversation.staff_id)
        .join(staff_user, staff_user.id == Staff.user_id)
        .filter(
            Conversation.clinic_id == user.clinic_id,
            or_(Patient.user_id == user.id, Staff.user_id == user.id),
        )
    )


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
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _summary(db: Session, conversation_id: uuid.UUID, user: User) -> ConversationPublic:
    row = _summary_query(db, user).filter(Conversation.id == conversation_id).first()
    if row is None:
        raise _not_found()
    return _to_public(row)


def get_conversation_for_user(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    conversation = (
        db.query(Conversation)
        .join(Patient, Patient.id == Conversation.patient_id)
        .join(Staff, Staff.id == Conversation.staff_id)
        .filter(
            Conversation.id == conversation_id,
            Conversation.clinic_id == user.clinic_id,
            or_(Patient.user_id == user.id, Staff.user_id == user.id),
        )
        .first()
    )
    if conversation is None:
        raise _not_found()
    return conversation


def _resolve_participants(
    db: Session, payload: ConversationCreateRequest, user: User
) -> tuple[Patient, Staff]:
    if user.role == UserRole.PATIENT:
        if payload.staff_id is None or payload.patient_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Indique apenas o profissional (staff_id) com quem pretende falar.",
            )
        patient = (
            db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
        )
        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Perfil de paciente não encontrado."
            )
        staff = (
            db.query(Staff).filter(Staff.id == payload.staff_id, Staff.clinic_id == user.clinic_id).first()
        )
        if staff is None or staff.staff_role not in CLINICAL_STAFF_ROLES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado.")
        # The care relationship that already exists in the data model: a
        # patient may only start a thread with a professional they have (or
        # had) an appointment with.
        has_appointment = (
            db.query(Appointment.id)
            .filter(
                Appointment.clinic_id == user.clinic_id,
                Appointment.patient_id == patient.id,
                Appointment.staff_id == staff.id,
            )
            .first()
        )
        if has_appointment is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Só pode iniciar conversas com profissionais com quem tem consultas.",
            )
        return patient, staff

    staff = clinical_staff(db, user)
    if payload.patient_id is None or payload.staff_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Indique apenas o paciente (patient_id) com quem pretende falar.",
        )
    patient = accessible_patient(db, payload.patient_id, user)
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
    conversation = get_conversation_for_user(db, conversation_id, user)
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
