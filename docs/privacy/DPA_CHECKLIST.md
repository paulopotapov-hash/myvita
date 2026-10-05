# Article 28 processor agreement checklist

**Not a contract and not legal advice.** A checklist of topics that the controller-processor agreement between each clinic and the myVita operator must address, and that the operator's agreements with sub-processors must flow down. The text, liability, pricing and governing law are for qualified legal review. **[DECISION: legal]**

Source of requirements: GDPR Art. 28(1)-(4) and (9) (written, including electronic, form), verified against EUR-Lex in this phase.

| # | Topic (Art. 28 reference) | What the agreement must cover | myVita technical fact that supports it | Status |
|---|---|---|---|---|
| 1 | Subject-matter, duration, nature, purpose, data types, data subject categories (28(3)) | Annex describing the processing | See [PROCESSING_ACTIVITIES.md](PROCESSING_ACTIVITIES.md) | Draft input ready |
| 2 | Documented instructions incl. transfers (28(3)(a)) | Operator acts only on written instructions; says so if an instruction infringes GDPR | No operator action on tenant data without a ticket (proposed in [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md)) | Process proposed |
| 3 | Confidentiality of personnel (28(3)(b), Art. 29, Art. 32(4)) | Named personnel bound by confidentiality | None defined | **Open** |
| 4 | Security measures (28(3)(c), Art. 32) | Annex of technical and organisational measures | Tenant isolation, RBAC, CSRF, Argon2id, session revocation, audit log, backups, monitoring; **gaps**: MFA, encryption-at-rest evidence, operator access control | Draft annex possible, gaps listed |
| 5 | Sub-processors (28(2), 28(4)) | Prior written authorisation (specific or general), notice of changes, flow-down of the same obligations, operator remains liable | [SUBPROCESSORS.md](SUBPROCESSORS.md) | Inventory and process ready; providers unselected |
| 6 | Assistance with data-subject rights (28(3)(e)) | Operator helps respond within the controller's deadlines | [DATA_SUBJECT_RIGHTS.md](DATA_SUBJECT_RIGHTS.md); no export tool yet | Procedure ready, tooling pending |
| 7 | Assistance with Arts. 32-36 (28(3)(f)) | Security, breach notification, DPIA, prior consultation support | [INCIDENT_RESPONSE_PRIVACY.md](INCIDENT_RESPONSE_PRIVACY.md), [DPIA_DRAFT.md](DPIA_DRAFT.md) | Ready |
| 8 | Breach notification by the processor (Art. 33(2)) | Notify the controller without undue delay after becoming aware; agree a concrete maximum interval | Procedure records the time of awareness | **Interval to be agreed** |
| 9 | Deletion or return at end of services (28(3)(g)) | Choice of the controller; delete existing copies unless law requires storage; backup cycle stated | [CLINIC_OFFBOARDING.md](CLINIC_OFFBOARDING.md), [RETENTION_MATRIX.md](RETENTION_MATRIX.md) | Procedure ready |
| 10 | Audits and information (28(3)(h)) | Make information available, allow audits/inspections | Documentation pack, audit log, test suite; no third-party audit | Scope to agree |
| 11 | International transfers | Locations and mechanisms disclosed; no transfer outside the EEA without authorisation | Unknown until hosting is chosen | **Open** |
| 12 | Liability and insurance | Allocation consistent with Art. 82 | n/a | Legal |
| 13 | Operator's own records (Art. 30(2)) | Operator maintains a processor-side record | Derived from the RoPA | Operator to maintain |
| 14 | DPO / contact points | Names and escalation contacts | None defined | **Open** |
| 15 | Service and security commitments | Availability targets (24 h RPO, 4 h RTO proposed, not contractual), backup retention, incident SLAs | `docs/operations.md` | Targets need owner approval |
| 16 | Customer-specific restrictions | Where clinic data may be hosted, who may access it | Hosting unselected | Open |

Also needed from the clinic side: controller identity, legal bases and Art. 9 condition, retention periods, who may instruct the operator, and the privacy-contact process for rights requests.
