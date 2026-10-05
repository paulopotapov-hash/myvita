# Roles, providers, transfers and subprocessor governance

Nothing here is a legal classification. It is a factual worksheet for the clinic, the operator and the DPO. **[DECISION: legal/DPO]** applies to every role assignment. Reference for the controller/processor test: GDPR Art. 4(7), 4(8), 28 and EDPB Guidelines 07/2020 on the concepts of controller and processor (not re-fetched in this phase; confirm the current version).

## 1. Who determines what (facts about how myVita is intended to operate)

| Question | Answer from the system and project documents | Open |
|---|---|---|
| Who determines purposes of clinical processing? | The clinic: its staff decide what is recorded about their patients; the software offers no clinical decision logic | Clinic type (private/public) changes the legal bases |
| Who determines essential means? | The clinic chooses what to enter and retain; the operator fixes the data model, hosting and security architecture | Retention and which fields are used must be set by the clinic, not by the operator |
| Who operates the infrastructure? | The myVita operator (entity **not yet defined**) | Legal entity, establishment country |
| Who accesses clinical data? | Clinic staff per RBAC; patients (own). Operators only through infrastructure access (see [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md)) | Operator access policy |
| Who manages users? | Clinic admins create/deactivate their own users | None |
| Who handles support? | **No support process exists** | Define before pilot |
| Who determines retention? | Nobody yet; the software enforces none | Controller decision |

## 2. Proposed role map

| Entity | Proposed role | Data accessed | Purpose | Contract needed | Location | Transfer mechanism | Review flag |
|---|---|---|---|---|---|---|---|
| Clinic / healthcare organisation | **Controller** of patient, staff and clinical data in its tenant | Its own tenant | Care delivery and administration | Controller-processor contract (Art. 28(3)) with the operator | Portugal **[TO CONFIRM]** | n/a | Confirm identity, DPO, legal bases |
| myVita operator | **Processor** for tenant data, on documented instructions. Possibly **controller** (or independent controller) for its own security/operations logs and platform account administration | Technically all tenants' data (infrastructure access); no application role | Provide and secure the service | Art. 28 contract; own RoPA as processor (Art. 30(2)) | **[TO CONFIRM]** | Depends on hosting | **Legal classification of log processing** |
| Hosting provider | **Sub-processor** of the operator | Everything stored on the host if not encrypted client-side | Run containers and storage | Art. 28(4) flow-down, DPA | **[TO CONFIRM]** | **[TO CONFIRM]** | Choose an EEA region; check provider's own sub-processors |
| Backup / object storage provider | **Sub-processor** | Full database dumps | Off-site recovery | Art. 28(4) flow-down, DPA | **[TO CONFIRM]** | **[TO CONFIRM]** | Confirm encryption, key ownership, region |
| Monitoring / alert receiver provider | Sub-processor **only if** it is a third-party service and receives personal data (today alerts carry no personal data) | Alert names, hostnames | Notify operators | Review if used | **[TO CONFIRM]** | **[TO CONFIRM]** | Keep alert payloads free of personal data |
| Email provider | **None**: no email is sent | n/a | n/a | n/a | n/a | n/a | Required review before adding |
| Support personnel | **None defined**; if staff of the operator ever access tenant data they act under the processor's authority (Art. 29) with confidentiality commitments | n/a | n/a | Confidentiality undertaking | n/a | n/a | Define access rules first |
| DNS / registrar / CA | Not processors of personal data (public domain data, certificates) | None | n/a | n/a | n/a | n/a | |
| Source hosting and CI (GitHub) and image registries | Not intended to hold personal data: repository and CI use synthetic data only (gitleaks configured; tests use `*.example` addresses) | None | Development | Developer terms | Outside scope of tenant data | n/a | Keep enforcing [PRODUCTION_DATA_POLICY.md](PRODUCTION_DATA_POLICY.md) |

## 3. Providers actually found in the repository

Searched backend code, frontend sources, `package.json`, requirements, compose files and workflows for email, AI/LLM, analytics, error-tracking, CDN and third-party API usage.

| Provider | Service | Purpose | Personal data received | Location | Contract / DPA | Sub-processor | Transfer | Notes |
|---|---|---|---|---|---|---|---|---|
| GitHub | Source control, Actions, optional GHCR | Development, CI, image publishing | None (synthetic only) | Provider-defined | Developer terms | No | Not applicable to tenant data | Secrets via Actions secrets, none committed |
| Docker Hub / public registries | Base images (`postgres`, `nginx`, `python`, `node`, Grafana, Prometheus ...) | Build | None | Provider-defined | n/a | No | n/a | Pin by digest for production (documented in P7) |
| **Hosting, backup bucket, alert receiver, DNS** | **Not yet selected** | | | | | | | Fill in on selection |

No email provider, no AI/LLM service, no analytics, no error tracking, no CDN, no third-party fonts, no external APIs exist. Do not list providers that are not used.

## 4. International transfers

- Primary hosting, backup location, alert receiver: **unknown**, therefore **no transfer assessment is possible yet**. The requirement is: choose EEA regions and EEA-established providers; if any personal data would leave the EEA (including provider support access from outside the EEA), flag for legal/DPO review and record the verified mechanism (adequacy decision under Art. 45 or Art. 46 safeguards). **No adequacy status or contractual clause is asserted here.**
- Today no code path sends personal data outside the host except the optional S3 upload.

## 5. AI / LLM privacy gate

No production AI or LLM functionality exists or is planned in the repository (no SDK, no API calls, no prompts). Gate for any future proposal, to be answered **before** development: exact data sent and whether it contains health data; provider and region; retention; use for training; contract and DPA; opt-out; human review; effect on the DPIA and the medical-device boundary (see [README.md](README.md)). Patient or clinical data must not be sent to a third-party model by default.

## 6. Subprocessor governance process (proportionate to a pilot)

| Step | Responsible | Trigger | Output |
|---|---|---|---|
| Propose provider | Operator lead | Need for a new service | One-page request: purpose, data categories, region |
| Security review | Operator security owner | Request | Checklist: encryption in transit/at rest, access control, logging, sub-processors, certifications, breach notification terms |
| DPA and location review | Operator + legal/DPO | After security review | Signed Art. 28 terms or rejection; region and transfer note |
| Approval | Controller(s) per contract (prior specific or general written authorisation, Art. 28(2)) | DPA OK | Approval record |
| Inventory update | Operator | Approval | Update section 3 and the RoPA |
| Change notification | Operator -> controllers | Any addition/replacement | Notice with time to object (Art. 28(2)) |
| Termination | Operator | End of service | Data deleted or returned (Art. 28(3)(g)), evidence kept |
| Annual review | Operator + DPO | Yearly | Re-confirm each provider |
