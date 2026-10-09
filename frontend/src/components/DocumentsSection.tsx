import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { LoadingSpinner } from './LoadingSpinner'
import { TextField } from './TextField'
import { useDownloadDocument, usePatientDocuments, useUploadDocument } from '../hooks/useDocuments'
import { ApiError } from '../lib/apiClient'
import { toUserMessage } from '../lib/errorMessages'
import { formatDateTime } from '../lib/formatDate'
import { fileTypeLabel, formatFileSize } from '../lib/formatFile'
import { DOCUMENT_ACCEPT, DOCUMENT_ALLOWED_TYPES, DOCUMENT_MAX_UPLOAD_BYTES, DOCUMENT_TITLE_MAX_LENGTH } from '../services/documents'

const PAGE_SIZE = 20
// 403 and 404 are deliberately indistinguishable here: the backend hides documents the
// caller may not act on, so the message must not hint whether the document exists.
const DOCUMENT_ACCESS_MESSAGE = 'Não tens acesso a este documento ou ele já não está disponível.'

function documentActionMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 403 || error.status === 404)) return DOCUMENT_ACCESS_MESSAGE
  return toUserMessage(error)
}

function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 413 || error.status === 422) && error.detail) return error.detail
  return documentActionMessage(error)
}

interface Props {
  patientId: string
  /** Doctor/nurse only — mirrors backend `clinical_staff` + `accessible_patient(write=True)`. */
  canManage: boolean
  /** Shown to clinical staff so it is obvious whose documents are on screen. */
  patientName?: string
}

export function DocumentsSection({ patientId, canManage, patientName }: Props) {
  const [page, setPage] = useState(1)
  const documents = usePatientDocuments(patientId, page, PAGE_SIZE)
  const upload = useUploadDocument(patientId)
  const download = useDownloadDocument()
  const fileInput = useRef<HTMLInputElement>(null)
  const [selected, setSelected] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [titleError, setTitleError] = useState('')
  const [uploadMessage, setUploadMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [actionError, setActionError] = useState('')
  // Deep link from a "Novo documento" notification: ?document=<id>.
  const [searchParams] = useSearchParams()
  const linkedId = searchParams.get('document')
  const linkedRow = useRef<HTMLLIElement>(null)
  const linkedVisible = Boolean(linkedId && documents.data?.items.some((item) => item.id === linkedId))

  useEffect(() => {
    if (!linkedVisible || !linkedRow.current) return
    linkedRow.current.focus()
    linkedRow.current.scrollIntoView?.({ block: 'center' })
  }, [linkedVisible])

  const total = documents.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function chooseFile(file: File | null) {
    setUploadMessage(null)
    if (!file) { setSelected(null); return }
    if (!DOCUMENT_ALLOWED_TYPES.has(file.type)) {
      setSelected(null)
      setUploadMessage({ tone: 'error', text: 'Formato não suportado. Envia um PDF, PNG ou JPEG.' })
      return
    }
    if (file.size > DOCUMENT_MAX_UPLOAD_BYTES) {
      setSelected(null)
      setUploadMessage({ tone: 'error', text: `O ficheiro excede o tamanho máximo de ${formatFileSize(DOCUMENT_MAX_UPLOAD_BYTES)}.` })
      return
    }
    setSelected(file)
  }

  function submitUpload(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || upload.isPending) return
    const trimmed = title.trim()
    if (!trimmed) {
      setTitleError('Indica um título para o documento.')
      return
    }
    setTitleError('')
    setUploadMessage(null)
    upload.mutate({ file: selected, title: trimmed }, {
      onSuccess: (created) => {
        setSelected(null)
        setTitle('')
        if (fileInput.current) fileInput.current.value = ''
        setPage(1)
        setUploadMessage({ tone: 'ok', text: `Documento “${created.title}” carregado com sucesso.` })
      },
      onError: (error) => setUploadMessage({ tone: 'error', text: uploadErrorMessage(error) }),
    })
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Documentos</h2>
          {patientName && <p className="text-sm text-slate-500">Documentos de {patientName}</p>}
        </div>
        {documents.data && <p className="text-sm text-slate-500">{total} {total === 1 ? 'documento' : 'documentos'}</p>}
      </div>

      {canManage && (
        <form className="mb-6 flex flex-col gap-3 border-b border-slate-100 pb-5" onSubmit={submitUpload} aria-label="Carregar documento" noValidate>
          <TextField
            label="Título do documento"
            required
            maxLength={DOCUMENT_TITLE_MAX_LENGTH}
            value={title}
            error={titleError}
            disabled={upload.isPending}
            onChange={(event) => { setTitle(event.target.value); if (titleError) setTitleError('') }}
          />
          <p className="text-xs text-slate-500">Os documentos não podem ser eliminados. Para corrigir um documento, carrega uma nova versão como novo documento.</p>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Novo documento (PDF, PNG ou JPEG até {formatFileSize(DOCUMENT_MAX_UPLOAD_BYTES)})
            <input
              ref={fileInput}
              type="file"
              accept={DOCUMENT_ACCEPT}
              disabled={upload.isPending}
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
              className="rounded-md border border-slate-300 px-3 py-2 font-normal file:mr-3 file:rounded-md file:border-0 file:bg-teal-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-teal-800"
            />
          </label>
          {selected && (
            <p className="text-sm text-slate-600">
              Selecionado: <span className="font-medium">{selected.name}</span> · {fileTypeLabel(selected.type)} · {formatFileSize(selected.size)}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!selected || upload.isPending} isLoading={upload.isPending}>
              {upload.isPending ? 'A carregar…' : 'Carregar documento'}
            </Button>
            {selected && !upload.isPending && (
              <Button variant="secondary" onClick={() => { chooseFile(null); if (fileInput.current) fileInput.current.value = '' }}>Limpar</Button>
            )}
          </div>
          {uploadMessage && (
            <p role={uploadMessage.tone === 'ok' ? 'status' : 'alert'} className={`text-sm ${uploadMessage.tone === 'ok' ? 'text-teal-700' : 'text-red-700'}`}>
              {uploadMessage.text}
            </p>
          )}
        </form>
      )}

      {actionError && <p role="alert" className="mb-3 text-sm text-red-700">{actionError}</p>}
      {documents.isLoading && <LoadingSpinner label="A carregar documentos…" />}
      {documents.isError && <ErrorState message={toUserMessage(documents.error)} onRetry={() => documents.refetch()} />}
      {documents.data?.items.length === 0 && (
        <EmptyState
          title="Sem documentos"
          description={canManage ? 'Ainda não foram carregados documentos para este paciente.' : 'Ainda não existem documentos disponíveis na sua ficha.'}
        />
      )}

      {documents.data && documents.data.items.length > 0 && (
        <ul className="divide-y divide-slate-100" aria-label="Lista de documentos">
          {documents.data.items.map((document) => {
            const downloading = download.isPending && download.variables?.documentId === document.id
            const linked = document.id === linkedId
            return (
              <li
                key={document.id}
                ref={linked ? linkedRow : undefined}
                tabIndex={linked ? -1 : undefined}
                aria-current={linked ? 'true' : undefined}
                className={`flex flex-col gap-3 py-4 outline-none sm:flex-row sm:items-center sm:justify-between ${linked ? '-mx-3 rounded-lg bg-teal-50 px-3 ring-2 ring-teal-600' : ''}`}
              >
                <div className="min-w-0">
                  <p className="truncate font-medium" title={document.title}>{document.title}</p>
                  <p className="truncate text-sm text-slate-600" title={document.original_filename}>{document.original_filename}</p>
                  <p className="text-sm text-slate-500">
                    {fileTypeLabel(document.content_type)} · {formatFileSize(document.file_size)} · {formatDateTime(document.created_at)}
                  </p>
                  <p className="text-xs text-slate-500">Carregado por {document.uploaded_by_name}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    isLoading={downloading}
                    disabled={download.isPending}
                    aria-label={`Transferir ${document.original_filename}`}
                    onClick={() => {
                      setActionError('')
                      download.mutate(
                        { documentId: document.id, fallbackName: document.original_filename },
                        { onError: (error) => setActionError(documentActionMessage(error)) },
                      )
                    }}
                  >
                    Transferir
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {documents.data && total > PAGE_SIZE && (
        <div className="mt-5 flex items-center justify-between gap-3">
          <Button variant="secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</Button>
          <span className="text-sm text-slate-500">Página {page} de {pages}</span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Seguinte</Button>
        </div>
      )}
    </section>
  )
}
