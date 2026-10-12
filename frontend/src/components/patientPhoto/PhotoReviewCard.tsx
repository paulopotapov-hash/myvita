import { useState } from 'react'
import { usePhotoDecision } from '../../hooks/usePatientPhoto'
import { toUserMessage } from '../../lib/errorMessages'
import { photoImageUrl } from '../../services/patientPhotos'
import type { PhotoRef } from '../../types/patientPhotos'
import { Avatar } from '../Avatar'
import { Button } from '../Button'
import { FormMessage } from '../FormMessage'
import { TextAreaField } from '../TextAreaField'

/**
 * "Foto de perfil por aprovar": shown only to the patient's associated doctor, and only
 * while a photo is pending (the server decides both).
 */
export function PhotoReviewCard({ name, pending }: { name: string; pending: PhotoRef }) {
  const decide = usePhotoDecision()
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  function submit(approve: boolean) {
    setError('')
    if (!approve && !reason.trim()) return setError('Indica o motivo, que o paciente vai ler.')
    decide.mutate(approve ? { photoId: pending.id, approve: true } : { photoId: pending.id, approve: false, reason: reason.trim() }, {
      onError: (failure) => setError(toUserMessage(failure)),
    })
  }

  return (
    <section aria-labelledby="photo-review" className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
      <h2 id="photo-review" className="text-base font-semibold text-amber-950">Foto de perfil por aprovar</h2>
      <div className="flex flex-wrap items-center gap-4">
        <Avatar name={name} size="xl" photoUrl={photoImageUrl(pending.id)} />
        <p className="max-w-md text-sm text-amber-950">
          Confirma que é uma foto a cores, com o rosto visível, sem filtros e só do próprio paciente.
        </p>
      </div>
      {error && <FormMessage kind="error">{error}</FormMessage>}
      {rejecting ? (
        <div className="flex flex-col gap-3">
          <TextAreaField label="Motivo da rejeição (o paciente vai ler)" value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
          <div className="flex flex-wrap gap-3">
            <Button isLoading={decide.isPending} onClick={() => submit(false)}>Rejeitar foto</Button>
            <Button variant="secondary" disabled={decide.isPending} onClick={() => setRejecting(false)}>Voltar</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          <Button isLoading={decide.isPending} onClick={() => submit(true)}>Aprovar</Button>
          <Button variant="secondary" disabled={decide.isPending} onClick={() => setRejecting(true)}>Rejeitar…</Button>
        </div>
      )}
    </section>
  )
}
