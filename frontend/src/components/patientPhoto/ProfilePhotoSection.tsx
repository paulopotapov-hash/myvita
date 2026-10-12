import { useRef, useState } from 'react'
import { useMyPhoto, useRemovePhoto, useUploadPhoto } from '../../hooks/usePatientPhoto'
import { toUserMessage } from '../../lib/errorMessages'
import { photoImageUrl } from '../../services/patientPhotos'
import { Avatar } from '../Avatar'
import { Button } from '../Button'
import { ConfirmDialog } from '../ConfirmDialog'
import { ErrorState } from '../ErrorState'
import { FormMessage } from '../FormMessage'
import { LoadingSpinner } from '../LoadingSpinner'
import { Modal } from '../Modal'
import { PhotoCropper } from './PhotoCropper'

const ACCEPTED = ['image/jpeg', 'image/png']
const MAX_BYTES = 5 * 1024 * 1024

/**
 * "Foto de perfil": take one with the phone's camera or pick one from the gallery, crop it
 * square, and send it for the doctor's approval. Until then it shows as "Pendente de
 * aprovação" here and the clinic keeps seeing the initials; an approved photo stays in use
 * until a newer one is approved.
 */
export function ProfilePhotoSection({ name }: { name: string }) {
  const photo = useMyPhoto()
  const upload = useUploadPhoto()
  const remove = useRemovePhoto()
  const cameraRef = useRef<HTMLInputElement>(null)
  const galleryRef = useRef<HTMLInputElement>(null)
  const [source, setSource] = useState<string | null>(null)
  const [removing, setRemoving] = useState<{ id: string; pending: boolean } | null>(null)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const data = photo.data

  function choose(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // the same file can be chosen again
    if (!file) return
    setMessage(null)
    if (!ACCEPTED.includes(file.type)) return setMessage({ kind: 'error', text: 'Escolhe uma fotografia em JPEG ou PNG.' })
    if (file.size > MAX_BYTES) return setMessage({ kind: 'error', text: 'A foto não pode ter mais de 5 MB.' })
    const reader = new FileReader()
    reader.onload = () => setSource(typeof reader.result === 'string' ? reader.result : null)
    reader.onerror = () => setMessage({ kind: 'error', text: 'Não foi possível ler esta imagem.' })
    reader.readAsDataURL(file)
  }

  function send(blob: Blob) {
    upload.mutate(blob, {
      onSuccess: () => {
        setSource(null)
        setMessage({ kind: 'success', text: 'Foto enviada. Fica pendente até o teu médico a aprovar.' })
      },
      onError: (error) => {
        setSource(null)
        setMessage({ kind: 'error', text: toUserMessage(error) })
      },
    })
  }

  return (
    <section aria-labelledby="profile-photo" className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5">
      <h2 id="profile-photo" className="text-base font-semibold text-slate-900">Foto de perfil</h2>
      {photo.isLoading && <LoadingSpinner label="A carregar a foto…" />}
      {photo.isError && <ErrorState message={toUserMessage(photo.error)} onRetry={() => photo.refetch()} />}
      {message && <FormMessage kind={message.kind}>{message.text}</FormMessage>}
      {data && (
        <>
          <div className="flex flex-wrap items-start gap-6">
            <figure className="flex flex-col items-center gap-2">
              <Avatar name={name} size="xl" photoUrl={data.approved ? photoImageUrl(data.approved.id) : null} />
              <figcaption className="text-xs text-slate-500">{data.approved ? 'Foto atual' : 'Sem foto aprovada'}</figcaption>
            </figure>
            {data.pending && (
              <figure className="flex flex-col items-center gap-2">
                <Avatar name={name} size="xl" photoUrl={photoImageUrl(data.pending.id)} />
                <figcaption className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-900">Pendente de aprovação</figcaption>
              </figure>
            )}
          </div>
          {data.rejected && (
            <FormMessage kind="error">A tua última foto não foi aprovada: {data.rejected.reason}</FormMessage>
          )}
          <div>
            <p className="text-sm font-medium text-slate-700">A foto tem de ser:</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-600">
              {data.requirements.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <p className="mt-1 text-xs text-slate-500">JPEG ou PNG, até 5 MB. O teu médico aprova a foto antes de a clínica a ver.</p>
          </div>
          <input ref={cameraRef} type="file" accept="image/jpeg,image/png" capture="user" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={choose} data-testid="photo-camera-input" />
          <input ref={galleryRef} type="file" accept="image/jpeg,image/png" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={choose} data-testid="photo-gallery-input" />
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => cameraRef.current?.click()}>Tirar foto</Button>
            <Button variant="secondary" onClick={() => galleryRef.current?.click()}>Escolher da galeria</Button>
            {data.pending && (
              <Button variant="secondary" onClick={() => setRemoving({ id: data.pending!.id, pending: true })}>Remover foto pendente</Button>
            )}
            {data.approved && (
              <Button variant="secondary" onClick={() => setRemoving({ id: data.approved!.id, pending: false })}>Remover foto</Button>
            )}
          </div>
        </>
      )}

      {source && (
        <Modal titleId="photo-crop-title" onClose={() => { if (!upload.isPending) setSource(null) }}>
          <h2 id="photo-crop-title" className="mb-4 text-lg font-semibold text-slate-900">Recortar a foto</h2>
          <PhotoCropper source={source} isPending={upload.isPending} onCancel={() => setSource(null)} onCrop={send} />
        </Modal>
      )}

      {removing && (
        <ConfirmDialog
          title={removing.pending ? 'Remover a foto pendente?' : 'Remover a foto?'}
          description="A foto é apagada de imediato e de forma definitiva."
          confirmLabel="Remover"
          isPending={remove.isPending}
          onCancel={() => setRemoving(null)}
          onConfirm={() =>
            remove.mutate(removing.id, {
              onSuccess: () => { setRemoving(null); setMessage({ kind: 'success', text: 'Foto removida.' }) },
              onError: (error) => { setRemoving(null); setMessage({ kind: 'error', text: toUserMessage(error) }) },
            })
          }
        />
      )}
    </section>
  )
}
