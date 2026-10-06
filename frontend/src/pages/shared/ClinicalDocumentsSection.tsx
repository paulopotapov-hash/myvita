import { useState } from 'react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { FormMessage } from '../../components/FormMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { TextAreaField } from '../../components/TextAreaField'
import { TextField } from '../../components/TextField'
import { useCreateDocumentNote, useDocumentHistory, useClinicalDocuments, useUpdateDocumentNote, useUploadClinicalDocument, useUploadDocumentVersion } from '../../hooks/useClinicalData'
import { clinicalDocumentsService } from '../../services/clinicalDocuments'
import { toUserMessage } from '../../lib/errorMessages'
import { formatDateTime } from '../../lib/formatDate'
import type { ClinicalDocumentPublic } from '../../types/api'
import { useSearchParams } from 'react-router-dom'

export function ClinicalDocumentsSection({ patientId, canWrite }: { patientId: string; canWrite: boolean }) {
  const documents = useClinicalDocuments(patientId)
  const createNote = useCreateDocumentNote(patientId)
  const updateNote = useUpdateDocumentNote(patientId)
  const upload = useUploadClinicalDocument(patientId)
  const uploadVersion = useUploadDocumentVersion(patientId)
  const [searchParams] = useSearchParams()
  const [selected, setSelected] = useState<ClinicalDocumentPublic | null>(null)
  const [editing, setEditing] = useState<ClinicalDocumentPublic | null>(null)
  const notificationDocument = documents.data?.find((item) => item.id === searchParams.get('document')) ?? null
  const selectedDocument = selected ?? notificationDocument
  const history = useDocumentHistory(selectedDocument?.id ?? '')
  const [noteTitle, setNoteTitle] = useState('')
  const [fileTitle, setFileTitle] = useState('')
  const [content, setContent] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const busy = createNote.isPending || updateNote.isPending || upload.isPending || uploadVersion.isPending

  function submitNote(event: React.FormEvent) {
    event.preventDefault()
    if (!noteTitle.trim() || !content.trim() || busy) {
      setError('Indica um título e o conteúdo da nota.')
      return
    }
    setError('')
    const options = {
      onSuccess: () => { setNoteTitle(''); setContent(''); setEditing(null); setSuccess('Nota guardada como nova versão.') },
      onError: (failure: unknown) => setError(toUserMessage(failure)),
    }
    if (editing?.kind === 'note') updateNote.mutate({ id: editing.id, payload: { title: noteTitle, content } }, options)
    else createNote.mutate({ title: noteTitle, content }, options)
  }

  function submitFile(event: React.FormEvent) {
    event.preventDefault()
    if (!file || !fileTitle.trim() || busy) { setError('Indica o título e escolhe um ficheiro PDF.'); return }
    if (file.size > 5 * 1024 * 1024) { setError('O ficheiro não pode exceder 5 MB.'); return }
    setError('')
    const onSuccess = () => { setFileTitle(''); setFile(null); setEditing(null); setSuccess('Ficheiro guardado como nova versão.') }
    if (editing?.kind === 'file') uploadVersion.mutate({ id: editing.id, title: fileTitle, file }, {
      onSuccess,
      onError: (failure) => setError(toUserMessage(failure)),
    })
    else upload.mutate({ title: fileTitle, file }, {
      onSuccess,
      onError: (failure) => setError(toUserMessage(failure)),
    })
  }

  async function download(document: ClinicalDocumentPublic, version?: number) {
    try {
      const blob = await clinicalDocumentsService.download(document.id, version)
      const href = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = href
      anchor.download = document.title.endsWith('.pdf') ? document.title : `${document.title}.pdf`
      anchor.click()
      URL.revokeObjectURL(href)
    } catch (failure) { setError(toUserMessage(failure)) }
  }

  return (
    <section aria-labelledby="documents-heading" className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 id="documents-heading" className="mb-4 text-lg font-medium">Documentos</h2>
      {canWrite && (
        <div className="mb-6 grid gap-6 border-b border-slate-100 pb-6 md:grid-cols-2">
          <form className="grid gap-3" onSubmit={submitNote}>
            <h3 className="font-medium">{editing?.kind === 'note' ? 'Nova versão da nota' : 'Nova nota'}</h3>
            <TextField label="Título da nota" required value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} maxLength={200} />
            <TextAreaField label="Conteúdo" required value={content} onChange={(event) => setContent(event.target.value)} maxLength={20000} />
            <Button type="submit" disabled={busy} isLoading={createNote.isPending || updateNote.isPending}>Guardar nota</Button>
          </form>
          <form className="grid content-start gap-3" onSubmit={submitFile}>
            <h3 className="font-medium">{editing?.kind === 'file' ? 'Nova versão do ficheiro' : 'Adicionar ficheiro PDF'}</h3>
            <TextField label="Título do ficheiro" required value={fileTitle} onChange={(event) => setFileTitle(event.target.value)} maxLength={200} />
            <label className="grid gap-1 text-sm font-medium text-slate-700">Ficheiro PDF
              <input aria-label="Ficheiro PDF" type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="block w-full rounded-md border border-slate-300 p-2 text-sm" />
              <span className="text-xs font-normal text-slate-500">PDF até 5 MB.</span>
            </label>
            <Button type="submit" variant="secondary" disabled={busy} isLoading={upload.isPending || uploadVersion.isPending}>Carregar ficheiro</Button>
          </form>
        </div>
      )}
      {error && <FormMessage kind="error" className="mb-3">{error}</FormMessage>}
      {success && <FormMessage kind="success" className="mb-3">{success}</FormMessage>}
      {documents.isLoading && <LoadingSpinner />}
      {documents.isError && <ErrorState message={toUserMessage(documents.error)} onRetry={() => documents.refetch()} />}
      {documents.data?.length === 0 && <EmptyState title="Sem documentos" description="Os ficheiros e notas partilhados pela equipa aparecerão aqui." />}
      {documents.data && documents.data.length > 0 && (
        <div className="grid gap-6 md:grid-cols-2">
          {(['file', 'note'] as const).map((kind) => {
            const rows = documents.data.filter((item) => item.kind === kind)
            return <div key={kind}>
              <h3 className="mb-2 font-medium">{kind === 'file' ? 'Ficheiros' : 'Notas'}</h3>
              {rows.length === 0 ? <p className="text-sm text-slate-500">Sem {kind === 'file' ? 'ficheiros' : 'notas'}.</p> : (
                <ul className="divide-y divide-slate-100">{rows.map((item) => (
                  <li key={item.id} className="py-3">
                    <p className="break-words font-medium">{item.title}</p>
                    <p className="text-xs text-slate-500">Versão {item.current_version} · Atualizado {formatDateTime(item.updated_at)}</p>
                    {item.current_author && <p className="text-xs text-slate-500">Atualizado por {item.current_author}</p>}
                    {item.current_content && <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-700">{item.current_content}</p>}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button variant="secondary" aria-label={`Ver versões de ${item.title}`} onClick={() => setSelected(selectedDocument?.id === item.id ? null : item)}>Histórico</Button>
                      {item.kind === 'file' && <Button variant="secondary" aria-label={`Descarregar ${item.title}`} onClick={() => download(item)}>Descarregar</Button>}
                      {canWrite && <Button variant="secondary" onClick={() => {
                        setEditing(item)
                        if (item.kind === 'note') { setNoteTitle(item.title); setContent('') }
                        else setFileTitle(item.title)
                        setSelected(item)
                      }}>Nova versão</Button>}
                    </div>
                    {selectedDocument?.id === item.id && <VersionHistory document={item} rows={history.data ?? []} loading={history.isLoading} error={history.isError} retry={() => history.refetch()} onDownload={(version) => download(item, version)} />}
                  </li>
                ))}</ul>
              )}
            </div>
          })}
        </div>
      )}
    </section>
  )
}

function VersionHistory({ document, rows, loading, error, retry, onDownload }: { document: ClinicalDocumentPublic; rows: import('../../types/api').ClinicalDocumentVersionPublic[]; loading: boolean; error: boolean; retry: () => void; onDownload: (version: number) => void }) {
  return <div className="mt-3 rounded-lg bg-slate-50 p-3" aria-label={`Histórico de ${document.title}`}>
    <h4 className="mb-2 text-sm font-medium">Histórico de versões</h4>
    {loading && <LoadingSpinner />}
    {error && <ErrorState message="Não foi possível carregar o histórico." onRetry={retry} />}
    {rows.map((row) => <div key={row.id} className="border-t border-slate-200 py-2 text-sm">
      <p className="font-medium">Versão {row.version}{row.is_current ? ' · Atual' : ''}</p>
      <p className="text-xs text-slate-600">{formatDateTime(row.created_at)} · {row.author_name}</p>
      {row.content && <p className="mt-1 whitespace-pre-wrap break-words">{row.content}</p>}
      {document.kind === 'file' && <Button variant="secondary" className="mt-1" aria-label={`Descarregar ${document.title}, versão ${row.version}`} onClick={() => onDownload(row.version)}>Descarregar versão {row.version}</Button>}
    </div>)}
  </div>
}
