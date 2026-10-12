/** Profile photo with the doctor's approval. Images are fetched from `photoImageUrl(id)`. */
export interface PhotoRef {
  id: string
  created_at: string
}

export interface MyPhoto {
  approved: PhotoRef | null
  /** Shown to the patient as "Pendente de aprovação". */
  pending: PhotoRef | null
  /** The doctor's reason, until the next upload. */
  rejected: { reason: string; rejected_at: string | null } | null
  requirements: string[]
}

/** Staff: the approved photo for the patient file; the pending one only for the approving doctor. */
export interface PatientPhotoStaff {
  approved: PhotoRef | null
  pending: PhotoRef | null
  can_review: boolean
}
