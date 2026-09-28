# Controlled clinical pilot runbook

## Before pilot

1. Select a reviewed release commit; confirm CI, security scans, migrations and immutable image builds.
2. Obtain privacy/legal gate approval and name clinic, operational, security, backup and incident owners.
3. Provision approved encrypted infrastructure, DNS/TLS and secret manager; configure exact hosts/CORS.
4. Prove off-site upload and isolated restore; record measured RPO/RTO evidence.
5. Deploy monitoring, configure human Alertmanager delivery and test firing/resolution.
6. Confirm public onboarding/registration and direct staff creation are off.
7. Verify health/readiness, migration revision and an empty/approved tenant state.

## Clinic bootstrap and onboarding

1. Externally verify the clinic and first clinic admin identity/contract.
2. Open the supervised clinic-onboarding switch only for the bootstrap request; create one clinic/admin over TLS; immediately disable it and verify it is closed.
3. Clinic admin creates doctor/nurse/admin-staff invitations. Deliver one-time fragment links only through the approved authenticated channel.
4. Recipient previews, accepts, chooses a strong private password and receives a session. Confirm role/clinic via `/auth/me` and audit event.
5. Clinic admin or doctor/nurse invites patients. Patient accepts and confirms own-only access.
6. Never send passwords, store invitation tokens, or create a permanent superadmin.

## During pilot

- review health/readiness, targets, alerts and backup freshness daily;
- review role assignments/cohort changes through the approved owner;
- keep support records free of passwords/tokens/clinical payloads;
- use account deactivation for offboarding/compromise and follow incident response;
- do not enable excluded features or expand tenants/cohort without gate review.

Password recovery is a controlled support escalation requiring approved identity verification and security-owner action; there is no self-service shortcut. MFA is **REQUIRED BEFORE PRODUCTION CLINICAL USE**. Reactivation and role changes require an approved procedure and currently have no application workflow.

## End of pilot

1. Stop new onboarding and traffic at the approved time.
2. Deactivate accounts/remove temporary operational access and verify old sessions fail.
3. Take and verify the final backup without overriding retention/legal instructions.
4. Produce only approved exports; never ad-hoc database dumps.
5. Apply the approved retention/deletion/restriction procedure across primary data, backups, logs and providers.
6. Record incidents, access changes, outcomes and disposal evidence; remove pilot secrets after required retention.
