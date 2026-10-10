# Clinical messaging

Clinical messaging is secure communication between a patient and their **current care team**. It is not a chat between arbitrary users. It is separate from Documents, Results and Medical Records. Implementation: `backend/app/modules/messages/`. UI: `frontend/src/pages/messages/`.

## Participants and access

- A conversation belongs to one patient and is opened by one doctor or nurse who has the messaging permission and an **active care assignment** to that patient (`staff_id` is the opener). One conversation exists per patient/opener pair.
- **Team inbox.** Every doctor and nurse currently assigned to the patient sees and can answer all of that patient's conversations. Access is re-evaluated on every request. Ending an assignment removes the conversations from that professional's inbox at once, and any direct access returns the same 404 as an unknown conversation.
- Patients see only their own conversations. They cannot start one; they reply in threads opened by the team.
- Physiotherapists, administrative staff and clinic administrators have no messaging access. Other clinics never see anything.
- A patient can reply only while the conversation is not closed and at least one active, assigned doctor or nurse could read the reply. This keeps a patient message from landing where nobody would read it.

## Lifecycle

| Status | Meaning | Set by |
|---|---|---|
| `open` | new or reopened | starting the conversation; a doctor reopening it |
| `waiting_for_team` | the patient wrote last | automatically, on a patient message; nurse triage |
| `waiting_for_patient` | the team wrote last | automatically, on a team message; nurse triage |
| `closed` | finished; read-only for everyone | a doctor only |

- **Triage.** Nurses (and doctors) can move a conversation between the three open states.
- **Escalation.** A nurse can request a doctor's review (`POST /conversations/{id}/escalate`). The care team's doctors get a generic notification, and the inbox can filter on `needs_review=true`. The request is resolved by a doctor's reply, or when a doctor closes the conversation. Repeating a pending request changes nothing.
- **Close and reopen.** Only a doctor closes (`POST /conversations/{id}/status`). The patient gets a generic notification. Closed conversations accept no messages from anyone, and the backend enforces it. Only a doctor reopens through the status endpoint. Starting a conversation again with the same patient reopens that clinician's closed thread; this is audited as a status change with `operation=start`.
- Triage metadata (review requested, by whom, who closed) is returned to staff only. The patient sees a simplified status.

## Messages and read state

- Plain text, 5,000 characters at most. There is no edit or delete endpoint; corrections are new messages. The runtime database role may update only `messages.read_at` and has no DELETE.
- Each message carries the sender's display name and role (patient, doctor, nurse) and `is_mine`. Internal user ids are not exposed.
- Read state is a shared team flag. The first care-team member who opens the thread marks the patient's messages read for the team. The patient marks the team's messages read. Staff never mark each other's messages.

## Notifications and audit

- Team message: the patient is notified. Patient message: every active, assigned doctor and nurse. Escalation: the assigned doctors. Close: the patient.
- Notifications use the central event module with fixed generic text and a deep link to the conversation, which is re-authorized on open. A burst of messages leaves one unread notification per recipient and conversation. Notification and message commit in the same transaction.
- Audited: conversation views (including inbox listing), creation, messages, reads, status changes (`from`/`to`), escalation, escalation cleared by a doctor's reply, and every denial (403/404). Audit rows hold identifiers and status codes, never message bodies.

## Deliberate limits

There is no real-time transport (refresh and query invalidation only), no attachments, no external e-mail or SMS for messages, no automatic doctor assignment, no response-time tracking and no medical-advice automation.

**Decisions required from the clinic before production use:**

- who monitors the team inbox and escalations, and expected response times;
- what patients are told about response times and emergencies;
- the retention period for conversations.

These depend on clinical governance and legal review; this implementation makes no service-level or compliance claim.
