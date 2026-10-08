import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentsSection } from './DocumentsSection'
import { ApiError, NetworkError } from '../lib/apiClient'
import { fileTypeLabel, formatFileSize } from '../lib/formatFile'
import type { DocumentPublic } from '../types/api'

const { state, uploadMutate, deleteMutate, downloadMutate } = vi.hoisted(() => ({
  state: {
    list: { data: undefined as { items: DocumentPublic[]; total: number } | undefined, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
    uploadPending: false,
    deletePending: false,
    downloadPending: false,
  },
  uploadMutate: vi.fn(),
  deleteMutate: vi.fn(),
  downloadMutate: vi.fn(),
}))

vi.mock('../hooks/useDocuments', () => ({
  usePatientDocuments: () => state.list,
  useUploadDocument: () => ({ mutate: uploadMutate, isPending: state.uploadPending }),
  useDeleteDocument: () => ({ mutate: deleteMutate, isPending: state.deletePending }),
  useDownloadDocument: () => ({ mutate: downloadMutate, isPending: state.downloadPending, variables: undefined }),
}))

const doc: DocumentPublic = {
  id: 'doc-1', patient_id: 'patient-1', uploaded_by_user_id: 'user-9',
  original_filename: 'analises.pdf', content_type: 'application/pdf', file_size: 204800, created_at: '2026-09-24T10:00:00Z',
}

function pdf(name = 'exame.pdf', size = 1024) {
  return new File([new Uint8Array(size)], name, { type: 'application/pdf' })
}

describe('DocumentsSection', () => {
  beforeEach(() => {
    uploadMutate.mockReset(); deleteMutate.mockReset(); downloadMutate.mockReset()
    state.list = { data: { items: [doc], total: 1 }, isLoading: false, isError: false, error: null, refetch: vi.fn() }
    state.uploadPending = false; state.deletePending = false; state.downloadPending = false
  })

  it('renders the Documentos title and the patient context for clinical staff', () => {
    render(<DocumentsSection patientId="patient-1" canManage patientName="Ana Silva" />)
    expect(screen.getByRole('heading', { name: 'Documentos' })).toBeInTheDocument()
    expect(screen.getByText('Documentos de Ana Silva')).toBeInTheDocument()
  })

  it('shows the loading state', () => {
    state.list = { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() }
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.getByText('A carregar documentos…')).toBeInTheDocument()
  })

  it('shows the empty state', () => {
    state.list.data = { items: [], total: 0 }
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.getByText('Sem documentos')).toBeInTheDocument()
  })

  it('lists documents with filename, type, size and upload date', () => {
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    const item = within(screen.getByRole('list', { name: 'Lista de documentos' })).getByRole('listitem')
    expect(item).toHaveTextContent('analises.pdf')
    expect(item).toHaveTextContent('PDF')
    expect(item).toHaveTextContent('200 KB')
    expect(item).toHaveTextContent('2026')
    expect(item).toHaveTextContent('Carregado por utilizador user-9')
  })

  it('shows a retryable error state and maps 403 to the shared message', async () => {
    const refetch = vi.fn()
    state.list = { data: undefined, isLoading: false, isError: true, error: new ApiError(403, 'HTTP 403'), refetch }
    render(<DocumentsSection patientId="patient-1" canManage />)
    expect(screen.getByText('Não tens permissão para aceder a este recurso.')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /tentar/i }))
    expect(refetch).toHaveBeenCalled()
  })

  it('does not expose upload or delete controls to patients', () => {
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    expect(screen.queryByRole('form', { name: 'Carregar documento' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Transferir analises.pdf' })).toBeInTheDocument()
  })

  it('shows the upload control only to clinical staff and previews the selected file', async () => {
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    const input = screen.getByLabelText(/Novo documento/) as HTMLInputElement
    expect(input.accept).toContain('application/pdf')
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeDisabled()
    await user.upload(input, pdf('exame.pdf', 2048))
    expect(screen.getByText('exame.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeEnabled()
  })

  it('rejects unsupported types and oversized files before calling the API', () => {
    render(<DocumentsSection patientId="patient-1" canManage />)
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

  it('uploads the selected file and reports success', async () => {
    uploadMutate.mockImplementation((_file: File, options: { onSuccess: (d: DocumentPublic) => void }) => options.onSuccess({ ...doc, original_filename: 'exame.pdf' }))
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    await user.upload(screen.getByLabelText(/Novo documento/), pdf())
    await user.click(screen.getByRole('button', { name: 'Carregar documento' }))
    expect(uploadMutate).toHaveBeenCalledWith(expect.any(File), expect.objectContaining({ onSuccess: expect.any(Function) }))
    expect(screen.getByRole('status')).toHaveTextContent('“exame.pdf” carregado com sucesso')
    expect(screen.getByRole('button', { name: 'Carregar documento' })).toBeDisabled()
  })

  it('surfaces the backend detail on upload failure', async () => {
    uploadMutate.mockImplementation((_file: File, options: { onError: (e: unknown) => void }) =>
      options.onError(new ApiError(422, 'HTTP 422', { detail: 'O conteúdo do ficheiro não corresponde ao formato indicado.' })))
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    await user.upload(screen.getByLabelText(/Novo documento/), pdf())
    await user.click(screen.getByRole('button', { name: 'Carregar documento' }))
    expect(screen.getByRole('alert')).toHaveTextContent('não corresponde ao formato indicado')
  })

  it('disables the file input and blocks resubmission while uploading', () => {
    state.uploadPending = true
    render(<DocumentsSection patientId="patient-1" canManage />)
    expect(screen.getByLabelText(/Novo documento/)).toBeDisabled()
    expect(screen.getByRole('button', { name: /A carregar/ })).toBeDisabled()
  })

  it('downloads through the authenticated API with a safe fallback filename', async () => {
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    expect(downloadMutate).toHaveBeenCalledWith({ documentId: 'doc-1', fallbackName: 'analises.pdf' }, expect.objectContaining({ onError: expect.any(Function) }))
  })

  it('shows network and not-found errors from download', async () => {
    downloadMutate.mockImplementationOnce((_v: unknown, o: { onError: (e: unknown) => void }) => o.onError(new NetworkError()))
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Sem ligação ao servidor')
    downloadMutate.mockImplementationOnce((_v: unknown, o: { onError: (e: unknown) => void }) => o.onError(new ApiError(404, 'HTTP 404', { detail: 'Documento não encontrado.' })))
    await user.click(screen.getByRole('button', { name: 'Transferir analises.pdf' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Documento não encontrado.')
  })

  it('asks for confirmation before deleting and cancels safely', async () => {
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    await user.click(screen.getByRole('button', { name: 'Eliminar analises.pdf' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('analises.pdf')
    await user.click(within(dialog).getByRole('button', { name: 'Voltar' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(deleteMutate).not.toHaveBeenCalled()
  })

  it('deletes after confirmation', async () => {
    deleteMutate.mockImplementation((_id: string, o: { onSuccess: () => void }) => o.onSuccess())
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    await user.click(screen.getByRole('button', { name: 'Eliminar analises.pdf' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Eliminar' }))
    expect(deleteMutate).toHaveBeenCalledWith('doc-1', expect.any(Object))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('reports delete failures instead of ignoring them', async () => {
    deleteMutate.mockImplementation((_id: string, o: { onError: (e: unknown) => void }) => o.onError(new ApiError(403, 'HTTP 403', { detail: 'Sem permissões clínicas.' })))
    const user = userEvent.setup()
    render(<DocumentsSection patientId="patient-1" canManage />)
    await user.click(screen.getByRole('button', { name: 'Eliminar analises.pdf' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Eliminar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Sem permissões clínicas.')
  })

  it('paginates with the server total', async () => {
    state.list.data = { items: [doc], total: 45 }
    render(<DocumentsSection patientId="patient-1" canManage={false} />)
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
