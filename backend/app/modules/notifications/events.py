"""Domain events that notify a user (P2.6), on top of the existing notifications table.

Every clinical workflow that tells someone "something happened" goes through
`notify()`. The rules live here instead of being repeated in each service:

- Privacy by construction. The title and text come from a fixed table keyed by
  the event; callers cannot pass free text, so no diagnosis, value, message
  body or document title can reach a notification.
- Same transaction as the business change. `notify()` only stages an INSERT on
  the caller's session; the caller's commit publishes the change and its
  notification together, and a rollback (failed validation, conflict, storage
  error) leaves neither behind. Nothing is sent before authorization succeeded,
  because services call it after their access checks.
- Recipient validated server-side. The row is inserted from a SELECT on
  `users` restricted to the event's clinic: a recipient from another clinic (or
  a deleted account) yields no notification instead of a cross-tenant one.
- Idempotent. Events with a natural identity pass a `dedupe_key`; the partial
  unique index on (user_id, event_key) turns a repeated event into a no-op.
- No noise. A new message does not stack a second notification while the
  recipient still has an unread one for the same conversation.

A notification is never an authorization: its deep link only names a target,
and the target's own endpoint re-checks the current permissions on open. A
record that is unshared, or an assignment that ends, takes effect immediately
however old the notification is.
"""

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import Boolean, String, and_, exists, literal, select
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import Session

from app.models import Notification, User


class NotificationEvent(str, enum.Enum):
    RESULT_AVAILABLE = "result_available"
    RESULT_CORRECTED = "result_corrected"
    MEDICAL_RECORD_SHARED = "medical_record_shared"
    DOCUMENT_ADDED = "document_added"
    MESSAGE_RECEIVED = "message_received"
    CONVERSATION_ESCALATED = "conversation_escalated"
    CONVERSATION_CLOSED = "conversation_closed"
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_ASSIGNED = "appointment_assigned"
    APPOINTMENT_UPDATED = "appointment_updated"
    APPOINTMENT_CONFIRMED = "appointment_confirmed"
    APPOINTMENT_COMPLETED = "appointment_completed"
    APPOINTMENT_NO_SHOW = "appointment_no_show"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    APPOINTMENT_CANCELLED_FOR_STAFF = "appointment_cancelled_for_staff"
    APPOINTMENT_REQUEST_RECEIVED = "appointment_request_received"
    APPOINTMENT_REQUEST_ACCEPTED = "appointment_request_accepted"
    APPOINTMENT_REQUEST_REJECTED = "appointment_request_rejected"
    APPOINTMENT_REQUEST_PROPOSED = "appointment_request_proposed"
    APPOINTMENT_REQUEST_ANSWERED = "appointment_request_answered"
    APPOINTMENT_REQUEST_REOPENED = "appointment_request_reopened"
    WAITLIST_OFFER = "waitlist_offer"
    APPOINTMENT_REMINDER = "appointment_reminder"


# Generic wording only. Existing texts are kept verbatim: the frontend and
# stored notifications rely on them (e.g. the message title).
TEMPLATES: dict[NotificationEvent, tuple[str, str]] = {
    NotificationEvent.RESULT_AVAILABLE: (
        "Novo resultado disponível",
        "Tem um novo resultado clínico disponível. Abra os resultados para o consultar.",
    ),
    NotificationEvent.RESULT_CORRECTED: (
        "Resultado corrigido",
        "Um dos seus resultados clínicos foi corrigido. Abra os resultados para consultar a versão atual.",
    ),
    NotificationEvent.MEDICAL_RECORD_SHARED: (
        "Nova informação clínica partilhada",
        "A equipa clínica partilhou consigo uma nota do seu registo clínico. Abra o registo clínico para a consultar.",
    ),
    NotificationEvent.DOCUMENT_ADDED: (
        "Novo documento",
        "A equipa clínica partilhou um novo documento. Abra os documentos para o consultar.",
    ),
    NotificationEvent.MESSAGE_RECEIVED: (
        "Nova mensagem",
        "Recebeu uma nova mensagem. Abra as mensagens para a ler.",
    ),
    NotificationEvent.CONVERSATION_ESCALATED: (
        "Conversa para revisão médica",
        "Uma conversa de um paciente foi sinalizada para revisão médica. Abra as mensagens para a consultar.",
    ),
    NotificationEvent.CONVERSATION_CLOSED: (
        "Conversa encerrada",
        "Uma conversa com a equipa clínica foi encerrada. Pode continuar a consultá-la nas mensagens.",
    ),
    NotificationEvent.APPOINTMENT_CREATED: ("Consulta criada", "Foi criada uma consulta na sua agenda."),
    NotificationEvent.APPOINTMENT_ASSIGNED: ("Consulta atribuída", "Foi atribuída uma consulta à sua agenda."),
    NotificationEvent.APPOINTMENT_UPDATED: ("Consulta atualizada", "Uma consulta da sua agenda foi atualizada."),
    NotificationEvent.APPOINTMENT_CONFIRMED: ("Consulta confirmada", "Uma consulta da sua agenda foi confirmada."),
    NotificationEvent.APPOINTMENT_COMPLETED: ("Consulta concluída", "Uma consulta da sua agenda foi concluída."),
    NotificationEvent.APPOINTMENT_NO_SHOW: (
        "Falta registada",
        "Foi registada uma falta numa consulta da sua agenda.",
    ),
    NotificationEvent.APPOINTMENT_CANCELLED: ("Consulta cancelada", "Uma consulta da sua agenda foi cancelada."),
    NotificationEvent.APPOINTMENT_CANCELLED_FOR_STAFF: (
        "Consulta cancelada",
        "Uma consulta atribuída à sua agenda foi cancelada.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_RECEIVED: (
        "Novo pedido de consulta",
        "Um paciente pediu uma consulta. Reveja os pedidos pendentes.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_ACCEPTED: (
        "Pedido de consulta aceite",
        "O seu pedido de consulta foi aceite e a consulta foi marcada.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_REJECTED: (
        "Pedido de consulta recusado",
        "O seu pedido de consulta não pôde ser aceite. Contacte a clínica se precisar.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_PROPOSED: (
        "Proposta de horário",
        "A clínica propôs um horário para o seu pedido de consulta. Abra as suas consultas para responder.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_ANSWERED: (
        "Resposta a uma proposta",
        "Um paciente respondeu a uma proposta de horário. Reveja os pedidos de consulta.",
    ),
    NotificationEvent.APPOINTMENT_REQUEST_REOPENED: (
        "Pedido de consulta reaberto",
        "O horário proposto a um paciente já não estava livre quando aceitou. Proponha outro horário.",
    ),
    NotificationEvent.WAITLIST_OFFER: (
        "Vaga mais cedo disponível",
        "Abriu uma vaga mais cedo para uma das suas consultas. Abra as suas consultas para a aceitar antes que expire.",
    ),
    NotificationEvent.APPOINTMENT_REMINDER: (
        "Lembrete de consulta",
        "Tem uma consulta marcada para breve. Abra-a para confirmar a presença ou, se ainda estiver no prazo, cancelar.",
    ),
}


class TargetType(str, enum.Enum):
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    RESULT = "result"
    MEDICAL_RECORD = "medical_record"
    APPOINTMENT = "appointment"


@dataclass(frozen=True)
class NotificationTarget:
    """Deep-link target. Each type uses its own same-clinic foreign key column."""

    type: TargetType
    id: uuid.UUID

    def columns(self) -> dict[str, uuid.UUID | None]:
        return {
            "target_id": self.id if self.type is TargetType.DOCUMENT else None,
            "conversation_target_id": self.id if self.type is TargetType.CONVERSATION else None,
            "result_target_id": self.id if self.type is TargetType.RESULT else None,
            "record_target_id": self.id if self.type is TargetType.MEDICAL_RECORD else None,
            "appointment_target_id": self.id if self.type is TargetType.APPOINTMENT else None,
        }


def notify(
    db: Session,
    event: NotificationEvent,
    *,
    clinic_id: uuid.UUID | str,
    recipient_user_id: uuid.UUID | str,
    target: NotificationTarget | None = None,
    dedupe_key: str | None = None,
    coalesce_unread: bool = False,
) -> None:
    """Stage the notification for `event` in the caller's transaction (see module docstring)."""
    title, message = TEMPLATES[event]
    clinic_uuid = uuid.UUID(str(clinic_id))
    recipient_uuid = uuid.UUID(str(recipient_user_id))
    target_columns = (
        target.columns()
        if target is not None
        else {
            "target_id": None,
            "conversation_target_id": None,
            "result_target_id": None,
            "record_target_id": None,
            "appointment_target_id": None,
        }
    )
    event_key = f"{event.value}:{dedupe_key}" if dedupe_key is not None else None

    # The target row (document, result, ...) must exist before the foreign key is checked.
    db.flush()

    conditions = [User.id == recipient_uuid, User.clinic_id == clinic_uuid]
    if coalesce_unread and target is not None:
        same_target = [
            getattr(Notification, column) == value for column, value in target_columns.items() if value is not None
        ]
        conditions.append(
            ~exists().where(
                and_(
                    Notification.user_id == recipient_uuid,
                    Notification.clinic_id == clinic_uuid,
                    Notification.is_read.is_(False),
                    *same_target,
                )
            )
        )

    columns = {
        "id": literal(uuid.uuid4(), UUID(as_uuid=True)),
        "clinic_id": literal(clinic_uuid, UUID(as_uuid=True)),
        "user_id": User.id,
        "title": literal(title, String()),
        "message": literal(message, String()),
        "target_type": literal(target.type.value if target is not None else None, String()),
        **{name: literal(value, UUID(as_uuid=True)) for name, value in target_columns.items()},
        "is_read": literal(False, Boolean()),
        "event_key": literal(event_key, String()),
    }
    statement = insert(Notification).from_select(
        list(columns), select(*[value.label(name) for name, value in columns.items()]).where(*conditions)
    )
    if event_key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=["user_id", "event_key"], index_where=Notification.event_key.isnot(None)
        )
    db.execute(statement)
