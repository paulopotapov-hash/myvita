# P6 operational ownership matrix

Placeholders must be replaced with named people/teams and tested contact paths before deployment. They are not assignments.

| Area | Owner | Backup owner | Escalation | Procedure |
|---|---|---|---|---|
| Infrastructure/network/TLS | `<ASSIGN_INFRA_OWNER>` | `<ASSIGN_INFRA_BACKUP>` | `<ASSIGN_INFRA_ESCALATION>` | deployment + incident runbooks |
| PostgreSQL/migrations | `<ASSIGN_DATABASE_OWNER>` | `<ASSIGN_DATABASE_BACKUP>` | incident lead | backup/restore + deployment |
| Application security/RBAC | `<ASSIGN_SECURITY_OWNER>` | `<ASSIGN_SECURITY_BACKUP>` | incident/privacy leads | security and incident runbooks |
| Backups/off-site restore | `<ASSIGN_BACKUP_OWNER>` | `<ASSIGN_BACKUP_BACKUP>` | infrastructure/incident | backup/restore runbook |
| Monitoring/alerting/on-call | `<ASSIGN_ONCALL_OWNER>` | `<ASSIGN_ONCALL_BACKUP>` | incident lead | monitoring runbook |
| Incident command | `<ASSIGN_INCIDENT_LEAD>` | `<ASSIGN_INCIDENT_BACKUP>` | executive/privacy/clinic | incident-response runbook |
| Deployments/rollback | `<ASSIGN_RELEASE_OWNER>` | `<ASSIGN_RELEASE_BACKUP>` | infrastructure/database | go-live checklist |
| Secrets/rotation | `<ASSIGN_SECRET_OWNER>` | `<ASSIGN_SECRET_BACKUP>` | security/incident | secrets inventory |
| Privacy/DPIA/requests | `<ASSIGN_PRIVACY_OWNER>` | `<ASSIGN_PRIVACY_BACKUP>` | legal/controller | data-protection checklist |
| Clinical pilot operations | `<ASSIGN_CLINIC_OWNER>` | `<ASSIGN_CLINIC_BACKUP>` | clinical governance/privacy | pilot runbook |

