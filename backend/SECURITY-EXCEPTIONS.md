# Dependency scan exceptions

There are currently no accepted dependency-vulnerability exceptions.

`pip-audit` is a blocking CI gate. A future exception must identify the
advisory, affected surface, compensating controls, owner, and review date;
it must never be added only to make CI green.

## Private patient document storage

Patient documents are stored in a configurable local directory
(`DOCUMENT_STORAGE_DIR`, default `/var/lib/myvita/documents`) outside the frontend
and static-file roots. The API stores random UUID-based keys, never derives paths from
original filenames, and serves bytes only through authenticated download
routes after clinic and patient authorization. Uploads are limited to PDF,
PNG, and JPEG by extension, declared MIME type, and basic file signature;
maximum size is configurable with `DOCUMENT_MAX_UPLOAD_BYTES` (10 MiB by
default). This validation is not malware scanning or content sanitization.
Operators must keep the directory private, include it in protected backup
plans, and restrict host-level access. This local storage is intended for a
single backend deployment; shared or multi-replica deployment needs a shared
private storage adapter before scaling.
