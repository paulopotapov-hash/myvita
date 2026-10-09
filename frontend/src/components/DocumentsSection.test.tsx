import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentsSection } from './DocumentsSection'
import { ApiError, NetworkError } from '../lib/apiClient'
import { fileTypeLabel, formatFileSize } from '../lib/formatFile'
import type { DocumentPublic } from '../types/api'

const { state, uploadMutate, downloadMutate } = vi.hoisted(() => ({
  state: {
    list: { data: undefined as { items: DocumentPublic[]; total: number } | undefined, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
    uploadPending: false,
    downloadPending: false,
  },
  uploadMutate: vi.fn(),
  downloadMutate: vi.fn(),
}))

vi.mock('../hooks/useDocuments', () => ({
  usePatientDocuments: () => state.list,
  useUploadDocument: () => ({ mutate: uploadMutate, isPending: state.uploadPending }),
  useDownloadDocument: () => ({ mutate: downloadMutate, isPending: state.downloadPending, variables: undefined }),
}))

const doc: DocumentPublic = {
  id: 'doc-1', patient_id: 'patient-1', title: 'Análises de rotina', uploaded_by_name: 'Dra. Rita Sousa',
  original_filename: 'analises.pdf', content_type: 'application/pdf', file_size: 204800, created_at: '2026-09-24T10:00:00Z',
}

/** The section reads the `?document=` deep link, so it renders inside a router. */
function renderSection(ui: ReactElement, url = '/patient/documentos') {
  return render(<MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>)
}

function pdf(name = 'exame.pdf', size = 1024) {
  return new File([new Uint8Array(size)], name, { type: 'application/pdf' })
}

describe('DocumentsSection', () => {
  beforeEach(() => {
    uploadMutate.mockReset(); downloadMutate.mockReset()
    state.list = { data: { items: [doc], total: 1 }, isLoading: false, isError: false, error: null, refetch: vi.fn() }
    state.uploadPending = false; state.downloadPending = false
  })

  it('renders the Documentos title and the patient context for clinical staff', () => {
    renderSection(<DocumentsSection patientId="patient-1" canManage patientName="Ana Silva" />)
    expect(screen.getByRole('heading', { name: 'Documentos' })).toBeInTheDocument()
    expect(screen.getByText('Documentos de Ana Silva')).toBeInTheDocument()
  })

  it('shows the loading state', () => {
    state.list = { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() }
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.getByText('A carregar documentos…')).toBeInTheDocument()
  })

  it('shows the empty state', () => {
    state.list.data = { items: [], total: 0 }
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.getByText('Sem documentos')).toBeInTheDocument()
  })

  it('lists documents with title, filename, type, size, upload date and the uploader name', () => {
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    const item = within(screen.getByRole('list', { name: 'Lista de documentos' })).getByRole('listitem')
    expect(item).toHaveTextContent('Análises de rotina')
    expect(item).toHaveTextContent('analises.pdf')
    expect(item).toHaveTextContent('PDF')
    expect(item).toHaveTextContent('200 KB')
    expect(item).toHaveTextContent('2026')
    // D2: a display name, never an internal user id.
    expect(item).toHaveTextContent('Carregado por Dra. Rita Sousa')
    expect(item).not.toHaveTextContent('utilizador')
  })

  it('highlights and focuses the document opened from a notification deep link', () => {
    const other: DocumentPublic = { ...doc, id: 'doc-2', title: 'Raio-X', original_filename: 'rx.png', content_type: 'image/png' }
    state.list.data = { items: [other, doc], total: 2 }
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />, '/patient/documentos?document=doc-1')
    const items = within(screen.getByRole('list', { name: 'Lista de documentos' })).getAllByRole('listitem')
    expect(items[1]).toHaveAttribute('aria-current', 'true')
    expect(items[1]).toHaveFocus()
    expect(items[0]).not.toHaveAttribute('aria-current')
  })

  it('shows a retryable error state and maps 403 to the shared message', async () => {
    const refetch = vi.fn()
    state.list = { data: undefined, isLoading: false, isError: true, error: new ApiError(403, 'HTTP 403'), refetch }
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    expect(screen.getByText('Não tens permissão para aceder a este recurso.')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /tentar/i }))
    expect(refetch).toHaveBeenCalled()
  })

  it('does not expose upload or delete controls to patients', () => {
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.queryByRole('form', { name: 'Carregar documento' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Transferir analises.pdf' })).toBeInTheDocument()
  })

  it('shows the upload control only to clinical staff and previews the selected file', async () => {
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    const input = screen.getByLabelText(/Novo documento/) as HTMLInputElement
    expect(input.accept).toContain('application/pdf')
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeDisabled()
    await user.upload(input, pdf('exame.pdf', 2048))
    expect(screen.getByText('exame.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeEnabled()
  })

  it('rejects unsupported types and oversized files before calling the API', () => {
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    const input = screen.getByLabelText(/Novo documento/)
    const docx = new File(['x'], 'macro.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(input, { target: { files: [docx] } })
    expect(screen.getByRole('alert')).toHaveTextContent('Formato não suportado')
    const big = pdf('grande.pdf', 1)
    Object.defineProperty(big, 'size', { value: 10 * 1024 * 1024 + 1 })
    fireEvent.change(input, { target: { files: [big] } })
    expect(screen.getByRole('alert')).toHaveTextContent('excede o tamanho máximo')
    expect(uploadMutate).not.toHaveBeenCalled()
  })

  it('requires a title before uploading (D5) and sends no request without one', async () => {
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    await user.upload(screen.getByLabelText(/Novo documento/), pdf())
    await user.type(screen.getByLabelText('Título do documento'), '   ')
    await user.click(screen.getByRole('button', { name: 'Carregar documento' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Indica um título para o documento.')
    expect(screen.getByLabelText('Título do documento')).toHaveAttribute('aria-invalid', 'true')
    expect(uploadMutate).not.toHaveBeenCalled()
  })

  it('uploads the selected file with its trimmed title and reports success', async () => {
    uploadMutate.mockImplementation((_payload: unknown, options: { onSuccess: (d: DocumentPublic) => void }) =>
      options.onSuccess({ ...doc, title: 'Exame de sangue', original_filename: 'exame.pdf' }))
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    await user.type(screen.getByLabelText('Título do documento'), '  Exame de sangue  ')
    await user.upload(screen.getByLabelText(/Novo documento/), pdf())
    await user.click(screen.getByRole('button', { name: 'Carregar documento' }))
    expect(uploadMutate).toHaveBeenCalledWith(
      { file: expect.any(File), title: 'Exame de sangue' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
    expect(screen.getByRole('status')).toHaveTextContent('“Exame de sangue” carregado com sucesso')
    expect(screen.getByLabelText('Título do documento')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeDisabled()
  })

  it('surfaces the backend detail on upload failure', async () => {
    uploadMutate.mockImplementation((_payload: unknown, options: { onError: (e: unknown) => void }) =>
      options.onError(new ApiError(422, 'HTTP 422', { detail: 'O conteúdo do ficheiro não corresponde ao formato indicado.' })))
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    await user.type(screen.getByLabelText('Título do documento'), 'Exame')
    await user.upload(screen.getByLabelText(/Novo documento/), pdf())
    await user.click(screen.getByRole('button', { name: 'Carregar documento' }))
    expect(screen.getByRole('alert')).toHaveTextContent('não corresponde ao formato indicado')
  })

  it('disables the file input and blocks resubmission while uploading', () => {
    state.uploadPending = true
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    expect(screen.getByLabelText(/Novo documento/)).toBeDisabled()
    expect(screen.getByRole('button', { name: /A carregar/ })).toBeDisabled()
  })

  it('downloads through the authenticated API with a safe fallback filename', async () => {
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    expect(downloadMutate).toHaveBeenCalledWith({ documentId: 'doc-1', fallbackName: 'analises.pdf' }, expect.objectContaining({ onError: expect.any(Function) }))
  })

  it('shows network and not-found errors from download', async () => {
    downloadMutate.mockImplementationOnce((_v: unknown, o: { onError: (e: unknown) => void }) => o.onError(new NetworkError()))
    const user = userEvent.setup()
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Sem ligação ao servidor')
    downloadMutate.mockImplementationOnce((_v: unknown, o: { onError: (e: unknown) => void }) => o.onError(new ApiError(404, 'HTTP 404', { detail: 'Documento não encontrado.' })))
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    // 403/404 map to one specific, non-revealing message (never the backend detail).
    expect(screen.getByRole('alert')).toHaveTextContent('Não tens acesso a este documento ou ele já não está disponível.')
  })

  it('offers no delete action, even to clinical staff: documents are append-only (D3)', () => {
    renderSection(<DocumentsSection patientId="patient-1" canManage />)
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByText(/não podem ser eliminados/)).toBeInTheDocument()
  })

  it('paginates with the server total', async () => {
    state.list.data = { items: [doc], total: 45 }
    renderSection(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  })

  it('formats sizes and types for humans', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2 KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.0 MB')
    expect(fileTypeLabel('image/jpeg')).toBe('JPEG')
    expect(fileTypeLabel('text/plain')).toBe('Ficheiro')
  })
})
