# First controlled clinical pilot

This document defines a proposed, configurable pilot envelope. It is not approval to process real patient data.

## Proposed envelope

- one verified clinic tenant;
- one clinic administrator, with a separately named operational owner;
- one or two doctors and one or two nurses;
- administrative staff only if scheduling requires it;
- a deliberately small patient cohort approved by the clinic/privacy owners.

These are starting parameters, not fixed product limits. Expansion requires a gate review of support capacity, access assignments, backup/restore evidence and privacy approval.

## Included and tested

- cookie-based login/logout and password change;
- clinic-scoped staff and patient invitations;
- patient directory with minimized administrative responses;
- operational appointment scheduling and clinical reason separation;
- patient-owned consent grant/revoke and clinician consent read;
- doctor/nurse medical records and medication workflows;
- patient self-access to own appointments, demographics, consents, records and medication;
- notifications, audit capture, account deactivation and session invalidation;
- health/readiness, migrations, local backup tooling and monitoring topology.

## Excluded from a first pilot

- public self-registration or public clinic onboarding;
- public internet deployment without approved TLS/domain and host controls;
- MFA, self-service password recovery, account reactivation and in-app role changes;
- bulk import/export, telemedicine, billing, prescriptions, lab/device integrations;
- proxy consent, clinician-recorded consent or legal-representative workflows;
- use beyond one approved tenant or outside the approved pilot cohort;
- any workflow not represented in the tested API and access matrix.

## Pilot gates

### Required before a real pilot

- reviewed release/CI, authentication, P4.1 authorization and tenant isolation;
- verified onboarding owner and private invitation-delivery channel;
- production secrets, encrypted storage, TLS/domain and exact CORS/trusted hosts;
- working local and off-site backups plus isolated restore evidence;
- deployed monitoring and a tested human alert destination;
- named operational/security/privacy owners and incident contacts;
- approved DPIA/privacy basis, notices, contracts, retention/deletion and support procedures.

### Not required for a local dry-run

- purchased domain or real certificate;
- production secret manager/provider credentials;
- real off-site bucket or human paging integration;
- real clinic/patient identities or clinical content;
- final legal approval, provided no real personal/clinical data is processed.

### Blocked by external infrastructure or decisions

Domain/DNS, renewable TLS, secret manager, encrypted production host/storage, immutable off-site backup, staffed alert destination, production host/network, approved invitation delivery, DPIA/privacy/legal decisions and named human owners are **BLOCKED — EXTERNAL INPUT REQUIRED**. Repository code or local simulation is not evidence that these are ready.
