# Patient profile photo

The patient adds a profile photo in **Perfil**; it is shown to the clinic only after the
patient's doctor approves it (MyChart-style). Code: `backend/app/modules/patient_photos/`,
`frontend/src/components/patientPhoto/`. Tests: `backend/tests/test_patient_photos.py`,
`frontend/e2e/patient-photo.spec.ts`.

## Flow

1. The patient takes a photo with the phone's camera, or picks one from the gallery, crops it
   square on the device and sends it. The requirements are shown next to the controls: in
   colour, face visible, no filters, only the patient.
2. The photo is **pending**. The patient sees it marked "Pendente de aprovação"; the clinic
   keeps seeing the initials. The patient's associated doctors get a notification linking to
   the patient's file, where a "Foto de perfil por aprovar" card is shown **only to them**,
   and only while a photo is pending. `GET /api/v1/patient-photos/pending-count` gives each
   doctor their number of pending photos, for the future staff inbox.
3. Only a **doctor with an active care assignment** to the patient approves or rejects (a
   rejection needs a reason). The patient is notified either way, with generic text; the
   reason is shown in the profile until the next upload.
4. Once approved, the photo is the patient's avatar and the image in the header of the
   staff patient file. A new photo is pending again; the approved one stays in use until the
   new one is approved. The patient may remove a pending or approved photo at any time.

## Protection (GDPR: a photo identifies the patient, so it is treated as health data)

- Stored in the private document storage (random key, directory `0700`), never under a
  public URL. Served only by `GET /api/v1/patient-photos/{id}/image`, which checks access on
  every request (`no-store`, `nosniff`, `inline`):
  - the patient: their own pending and approved photo;
  - staff who may open the patient's file: the approved photo only;
  - the approving doctors: the pending photo too;
  - anyone else gets the same 403/404 as for the patient file; another clinic gets 404.
- Upload: JPEG or PNG only, at most 5 MB (also enforced by the proxy and the request-size
  middleware for this one path), judged by content: file signature, then the image decoder.
  Decompression bombs, images under 200x200 and black-and-white photos ("A foto tem de ser
  a cores") are refused. The camera orientation is applied, then the photo is cropped,
  resized to **512x512** and re-encoded as a new JPEG: no EXIF (GPS location, device,
  dates), ICC or XMP survives. The original file name is never stored.
- Rate limit per user: 5 uploads per hour and 20 per day.
- Audit (identifiers only, never the image, a file name or the rejection reason):
  `patient_photo_uploaded`, `_approved`, `_rejected`, `_removed`, `_deleted`.

## Retention (decision of 2026-10-12)

A photo no longer in use is **deleted at once and for good**, its file and its row:

- the previous approved photo, when a newer one is approved;
- a pending photo replaced by a newer upload;
- a rejected photo's image (only the reason is kept, without the image, until the patient
  uploads another photo; then that row is deleted too);
- any photo the patient removes.

There is no grace period. The runtime database role has DELETE on `patient_photos` only
(`backend/app/db_provisioning.py`); every other restricted table still has none.

**Reliable file deletion.** The row is deleted in the same transaction that queues the file
in `storage_deletions`; the file is removed right after the commit. If that fails (I/O error,
permissions) or the process stops in between, the entry stays queued and the background job
(`python -m app.jobs`, every minute) retries until the file is gone, then marks it done.
Queue entries hold only the random storage key. The deploy checklist checks the queue.

**Backups.** Database dumps and the document-volume backups taken before a deletion still
contain the photo, until those backups expire under the backup retention policy
(`docs/p7-backup-and-restore.md`). Restoring an old backup can bring a deleted photo back; if
that happens, the patient's current choice must be applied again (remove the photo).
