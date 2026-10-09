# myVita — Phase 6 UAT Scenarios

Implemented in `frontend/e2e/uat.spec.ts`. "B" = exercised through the browser, "A" = through the API.
Result column: outcome on the final build (see `PHASE6_REPORT.md` for the run).

| ID | Scenario | Channel | What is checked |
| --- | --- | --- | --- |
| UAT-01 | Patient login, navigation, refresh, logout | B | Login lands on `/patient`; all patient pages open; refresh keeps the session; logout returns to login |
| UAT-02 | Patient sees own appointment and a generic notification | B | Own data visible; notification text contains no clinical detail |
| UAT-03 | Doctor finds and opens a patient of own clinic | B | Search, list, open record |
| UAT-04 | Clinic A cannot reach clinic B | A+B | Every role in A gets 404/403 on B's patients, appointments, records, medications, staff; lists never contain B |
| UAT-05 | Clinic admin invites staff; invitee works | A+B | Invitation accept, session, first actions |
| UAT-06 | Disabled staff cannot log in; live session ends at once | A+B | Deactivation revokes the existing session and blocks new login; reactivation works |
| UAT-07 | Patient cannot access another patient | A | Same-clinic and cross-clinic IDs rejected |
| UAT-08 | Nurse has clinical rights, not doctor-only or admin-only rights | A | Permission matrix for nurse |
| UAT-09 | Administrative staff run the agenda but see no clinical content | A | Appointment reason, records and medications hidden or forbidden |
| UAT-10 | Doctor books an appointment in the browser; double click and conflicts do not duplicate | B+A | One appointment on double click; same slot returns 409; invalid input returns 404/422 |
| UAT-11 | Clinical record lifecycle | A+B | Create, versioned update, stale update 409, revision history, patient can read, patient cannot write, other patient gets 404 |
| UAT-12 | Medications | A | Create, edit, deactivate, invalid values, isolation |
| UAT-13 | Notifications | A | Generic text, own-only, mark read, idempotent |
| UAT-14 | Consent | A | Only the patient records it; history, revoke, duplicates. Consent does **not** gate clinical access (documented limit) |
| UAT-15 | Clinic admin manages team, not another clinic | A | Role change, deactivate, cross-clinic rejected |
| UAT-16 | Authentication negatives | A | Wrong password, unknown user, disabled user look identical; rate limiting; no leakage |
| UAT-17 | Password change and logout revoke other sessions | A+B | Other sessions end; protected pages do not survive logout |
| UAT-18 | Audit evidence | DB | Read after the run: events present, no secrets or clinical text |
| UAT-19 | Clean errors | A | No stack traces, SQL or file paths; `X-Request-ID` returned |
| UAT-20 | UI recovers from backend outage, refresh, back/forward | B | Error state shown, recovery on retry, unknown route handled, offline then online |
| UAT-21 | Responsive layout | B | No horizontal overflow at phone and tablet widths |
| UAT-22 | Accessibility | B | Keyboard-only login; axe A/AA no serious/critical on login, 6 staff pages and 7 patient pages; every patient page has an `h1` |

## Not covered by any scenario

Print/export, email or SMS delivery (not implemented), file attachments (not implemented),
MFA and password recovery (not implemented), multi-language, browsers other than Chromium.
