# Clinical Documents

## Product boundary

**Documents** hold patient-facing files and authored guidance. **Medical Records** remain the clinical history and observations; **Medications** remain structured medication data. Notes created here live under Documents and do not reuse medical-record revisions. Messaging and team inbox are not part of this feature.

Documents currently support two kinds: text notes and PDF files. Notes and file replacements create immutable numbered versions; a document's `current_version` points to the newest version. Previous text and file versions remain retrievable to authorized users. Permanent deletion is not exposed.

## Access and audit

Patient reads use the patient's authenticated profile. Doctor and nurse actions use the central `ClinicalAction` policy and an active Phase 1 patient assignment. The current pilot gives doctor and nurse the same document actions, matching their existing clinical write scope; other roles, including physiotherapists and administrative staff, receive no document access. Changing this policy requires an explicit product/security review.

List, detail, version-history and download requests authorize independently. Tenant-scoped foreign keys add database protection. Document create/update/view/download and denials use the existing append-only audit trail. Audit metadata contains identifiers only, never note content or file bytes.

## Storage and file handling

PostgreSQL stores metadata, note content and opaque version references, not file bytes. The domain uses a storage protocol with a private local filesystem implementation. PDFs are kept in a private directory with generated 128-bit opaque keys, exclusive file creation, restrictive file permissions and SHA-256 checksums. Original filenames are metadata only and are never used as storage paths; internal storage keys and checksums are not returned to clients. Uploads are limited to PDF, checked against extension, declared MIME type and the `%PDF-` signature, and limited to 5 MiB. Downloads are attachments with `nosniff` and `no-store` headers.

Development Compose mounts `backend/var/documents`; production Compose mounts a dedicated `myvita_documents` volume at `/var/lib/myvita/documents`. This abstraction is local-filesystem-specific today; an object-storage backend is future work. No custom encryption is implemented and no at-rest encryption claim is made. Operators must protect/encrypt the underlying volume and transport with their infrastructure controls.

**Production limitation:** the current scheduled backup and off-site backup pipeline archives PostgreSQL only; it does not yet archive or restore `myvita_documents`. Configure and verify an independent protected backup/restore for this volume before using Documents for production clinical records. No public/static file URLs are issued. PDF active-content sanitization and malware scanning are not implemented; the MVP stores PDFs as attachments and does not render them inline.

### What was validated locally (Phase 4)

On a local production-shaped Compose stack (`docker-compose.prod.yml` + `docker-compose.prod-http.yml`, throwaway secrets), through the public proxy:

- PDF upload, new version, download of current and previous versions (byte-identical by SHA-256), and rejection of traversal names, wrong extension/MIME/signature and oversized files.
- Files survive `docker compose down` / `up` because they live in the named `myvita_documents` volume.
- A manual volume backup and restore works: stop the backend, archive the volume read-only, and restore it with ownership and `0600` permissions preserved:

  ```bash
  docker run --rm --user 0 -v <project>_myvita_documents:/data:ro -v "$PWD":/out --entrypoint sh <backend-image> -c 'tar -cf /out/documents.tar -C /data .'
  docker run --rm --user 0 -v <project>_myvita_documents:/data -v "$PWD":/in:ro --entrypoint sh <backend-image> -c 'tar -xpf /in/documents.tar -C /data'
  ```

  With the volume emptied, downloads fail with a 404 that discloses no path; after the restore they succeed with identical checksums.

Not validated: scheduling, encryption, off-site copies and retention for this archive, and keeping it consistent with the PostgreSQL backup (metadata rows and files must be restored to the same point in time). **Document storage backup/restore requires production infrastructure validation before production deployment.**

## Notifications

Creating a document and each new version inserts one patient notification in the same database transaction. The notification contains a short title/message and a typed document target; the document remains the source of content. Only the patient account receives the notification. Opening its link returns through the authenticated Documents API, which rechecks authorization.

## API

- `GET /api/v1/patients/{patient_id}/documents` and `GET /api/v1/documents/mine`
- `POST /api/v1/patients/{patient_id}/documents/notes`
- `POST /api/v1/patients/{patient_id}/documents/files` (multipart PDF)
- `GET /api/v1/documents/{id}`
- `PATCH /api/v1/documents/{id}/notes`
- `POST /api/v1/documents/{id}/files/versions` (multipart PDF replacement)
- `GET /api/v1/documents/{id}/versions` and `GET /api/v1/documents/{id}/versions/{number}`
- `GET /api/v1/documents/{id}/download` and `GET /api/v1/documents/{id}/versions/{number}/download`

These are technical controls intended to support privacy and access control; they are not a legal compliance certification.
