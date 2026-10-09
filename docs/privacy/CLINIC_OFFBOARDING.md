# Clinic offboarding

Trigger: contract end, clinic decision to leave, or operator decision to stop service. The clinic (controller) decides return and deletion; the operator (processor) executes on written instruction (GDPR Art. 28(3)(g): at the controller's choice, delete or return all personal data and delete existing copies unless law requires storage). **Do not delete anything without the controller's written confirmation and a legal check of retention duties.** **[DECISION: controller/legal]**

No software support exists for bulk export or clinic deletion; both are operator procedures under the break-glass rules in [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md).

| Step | Responsible | Action | Technical notes | Evidence |
|---|---|---|---|---|
| 1 Notice and plan | Clinic contact + operator lead | Agree dates, scope, return format, who receives data, retention duties | Check for open rights requests and legal holds | Signed offboarding plan |
| 2 Freeze new processing | Clinic admin | Stop onboarding and invitations; deactivate staff and patients at the agreed cut-off (`POST /staff/{id}/deactivate`, `POST /patients/{id}/deactivate`) | Deactivation revokes sessions immediately | Audit `user_disabled` rows; clinic admin confirmation |
| 3 Return data (if required) | Operator on instruction | Produce a per-clinic export from a restored or read-only copy: `WHERE clinic_id = <clinic>` across all tables; deliver over a secure channel with a checksum; exclude other clinics' rows | No export API exists; a documented SQL extract is the method. Test it on synthetic data first; the schema is the format description | Export manifest: tables, row counts, checksum, recipient, date |
| 4 Confirm receipt | Clinic contact | Written acknowledgement | | Acknowledgement |
| 5 Retention hold | Controller/legal | Decide which data must be kept by law (clinical records) and where, since the platform will stop | Do not leave data with the operator without a continuing contract | Retention decision |
| 6 Delete from production | Operator on written instruction | Delete the clinic's rows in dependency order in a single audited transaction (patients' clinical rows first because of `RESTRICT`, then appointments/notifications, staff, users, then the clinic). Audit rows keep `clinic_id` as `NULL` after deletion (`SET NULL`) | No delete tool exists; write and test one against synthetic data before use. `actor_email` in audit rows remains personal data and needs its own decision | Deletion script, row counts before/after, second-person review |
| 7 Backups | Operator | State when the data will leave backups: local 14 days, off-site 30 days by default. If earlier removal is required, expire or re-create backups only under incident-level approval | Restores before expiry would bring the clinic back: record a "do not restore clinic X" note in the restore runbook | Backup expiry date recorded |
| 8 Logs | Operator | Application and proxy logs rotate out; audit rows per decision | | Statement of residual data and dates |
| 9 Access and secrets | Operator | Remove clinic admins; rotate anything shared; delete invitations and test accounts | | Access review snapshot |
| 10 Confirmation | Operator -> clinic | Written confirmation of what was returned, deleted, retained, and when residual copies expire | | Offboarding certificate |

Offboarding is a rehearsable procedure: run steps 3 and 6 on a synthetic clinic in staging before the first real pilot, and keep the scripts under version control.
