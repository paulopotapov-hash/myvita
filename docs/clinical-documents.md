# Clinical documents

Patient files (reports, images) stored privately and shown to the patient and their care team. Implementation: `backend/app/modules/documents/`. UI: `frontend/src/components/DocumentsSection.tsx`.

## Access

- **Upload:** a doctor or nurse with an **active care assignment** to the patient (`EDIT_DOCUMENTS`). The patient, the clinic and the uploader come from the URL and the session, never from the body.
- **List and download:** the patient (own documents only) and assigned doctors or nurses. Every request re-checks tenant, role and assignment.
- Other patients, other clinics, physiotherapists, administrative staff and clinic administrators are denied. Every denial is audited against the requested resource.
- A clinical result may reference a document of the **same** patient and clinic. The service checks this, and a composite foreign key enforces it. The document keeps its own access rules: a result never grants access to a document.

## Upload rules

- PDF, PNG or JPEG only. The extension, the declared content type and the file signature (magic bytes) must all agree.
- Size limit `DOCUMENT_MAX_UPLOAD_BYTES` (default 10 MiB), enforced while streaming. The proxy allows 11 MiB on the upload path only.
- A title is required. The original filename is metadata only, restricted to a safe character set, and never used as a storage path.

## Storage

- Files live in a private directory (`DOCUMENT_STORAGE_DIR`; in production the `myvita_documents` volume at `/var/lib/myvita/documents`, mode 0700).
- Each file is stored under a random 128-bit key (`[0-9a-f]{32}`). Paths are resolved and confined to the storage root. Files are created exclusively, so nothing is ever overwritten.
- **Consistency.** The file is written and fsynced first, then the database row and the patient's notification are committed together. If the write fails, the partial file is removed. If the database step fails, the stored file is removed. A committed document therefore always has its complete file; a failure leaves neither behind.
- Storage keys, paths and checksums are never returned to clients.
- There are no public or static URLs. Downloads go through the authenticated API as attachments, with `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`.
- **Append-only.** There is no delete or edit route, and the runtime database role cannot UPDATE or DELETE document rows. A correction is a new document. Deletion waits for a validated retention policy (`privacy/RETENTION_MATRIX.md`).

## Notifications and audit

- A new document notifies the patient once, with generic text ("Novo documento") and a deep link that re-checks access. The notification commits in the same transaction as the row.
- Audited: upload, list view, download and every denial. Identifiers only, never titles or file contents.

## Operations

- **Health.** `myvita_document_storage_writable` (on the internal metrics endpoint) drives the `MyVitaDocumentStorageUnavailable` alert. Upload failures caused by storage return 503 without disclosing paths.
- **Backup and restore.** The scheduled backup archives the documents volume after the database dump, encrypts it client-side for off-site storage, and `verify_documents_storage.sh` / `verify_restore.sh` check that every row has its file. See `p7-backup-and-restore.md` for the consistency model.
- **Encryption at rest** depends on the host volume or disk encryption; the application does not encrypt files itself.

## Not implemented (product roadmap, not in scope)

- Document versions and version history.
- Text-note documents.
- Malware scanning and PDF active-content sanitisation. PDFs are served as downloads, never rendered inline by the app.
- An object-storage backend.
