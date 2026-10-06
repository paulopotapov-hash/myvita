# Clinical messaging

Clinical messaging is a patient communication channel separate from Documents and Medical Records. A doctor or nurse with an active Phase 1 care assignment starts each conversation and sends the first message. Patients can only reply to existing conversations; they cannot open a new conversation with the clinic.

## Access and workflow

- Conversations are clinic and patient scoped. Every inbox, conversation, reply, status, and escalation request rechecks the shared clinical access policy and active patient assignment.
- Doctors and nurses can read, start and reply to conversations for assigned patients. Physiotherapists and administrative roles receive no messaging permission in the current policy.
- Nurses can change non-closed statuses and explicitly flag a conversation for doctor review. Only a doctor may close a conversation. A doctor reply clears the outstanding review flag.
- Patients see only their own conversations and can reply while a conversation is open. A closed conversation is read-only.
- The team inbox is shared by currently authorized assigned doctors and nurses. The first staff member opening a patient reply clears the shared team unread flag.

## Notifications and audit

Team messages notify the patient. Patient replies notify active assigned doctors and nurses. Nurse escalation notifies only active assigned doctors. Notifications contain a short generic message and typed conversation reference, never the message body. Opening the link rechecks authorization through the conversation API.

Conversation views, creation, messages, status changes, escalations, escalation resolution by a doctor reply, and denied access use the existing append-only audit log. Audit entries contain conversation identifiers and limited status metadata, not message bodies.

Messages have no edit or delete endpoint. A database trigger rejects message row updates and deletes, and the runtime database role has insert-only access with no truncate privilege. Correcting a message requires another message.

## Deliberate limits and decisions

There is no doctor auto-assignment, complex queue, external email/SMS, attachment, real-time transport, or medical advice automation. Inbox updates use explicit refresh and normal query invalidation. The shared team unread flag means one authorized staff member reading a reply clears it for the team; per-user read state is deferred.

The clinic must decide its operational retention period, who is responsible for monitoring escalations, and expected response times before production use. Those policies depend on the clinic's clinical governance and applicable legal review; this implementation does not make a compliance certification or define clinical service-level commitments.
