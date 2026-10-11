import { useState } from 'react'
import { ConfirmDialog } from './ConfirmDialog'
import { TextAreaField } from './TextAreaField'

interface Props {
  title: string
  description: string
  confirmLabel: string
  /** Omit for actions that need no reason (e.g. a patient removing their own declaration). */
  reasonLabel?: string
  isPending?: boolean
  /** Server-side problem to show inside the dialog. */
  error?: string
  onConfirm: (reason: string) => void
  onCancel: () => void
}

/** Confirmation that can require a written reason (hiding from the patient, deleting). */
export function ReasonDialog({ title, description, confirmLabel, reasonLabel, isPending, error, onConfirm, onCancel }: Props) {
  const [reason, setReason] = useState('')
  const [missing, setMissing] = useState(false)
  return (
    <ConfirmDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      isPending={isPending}
      onCancel={onCancel}
      onConfirm={() => {
        if (reasonLabel && !reason.trim()) {
          setMissing(true)
          return
        }
        onConfirm(reason.trim())
      }}
    >
      {reasonLabel && (
        <div className="mt-4">
          <TextAreaField
            label={reasonLabel}
            value={reason}
            maxLength={500}
            required
            error={missing ? 'Indica o motivo.' : undefined}
            onChange={(event) => {
              setReason(event.target.value)
              setMissing(false)
            }}
          />
        </div>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
    </ConfirmDialog>
  )
}
