import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { ClinicalDocumentPublic, ClinicalDocumentVersionPublic } from '../../types/api'
import { ClinicalDocumentsSection } from './ClinicalDocumentsSection'

const state = vi.hoisted(() => ({
  documents: { data: [] as ClinicalDocumentPublic[] | undefined, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  history: { data: [] as ClinicalDocumentVersionPublic[] | undefined, isLoading: false, isError: false, refetch: vi.fn() },
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
  upload: { mutate: vi.fn(), isPending: false },
  uploadVersion: { mutate: vi.fn(), isPending: false },
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useClinicalDocuments: () => state.documents,
  useDocumentHistory: () => state.history,
  useCreateDocumentNote: () => state.create,
  useUpdateDocumentNote: () => state.update,
  useUploadClinicalDocument: () => state.upload,
  useUploadDocumentVersion: () => state.uploadVersion,
}))

const note: ClinicalDocumentPublic = {
  id: 'note-1', clinic_id: 'clinic-1', patient_id: 'patient-1',
  kind: 'note', title: 'Plano de cuidados', current_version: 2,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-02T10:00:00Z',
  current_content: 'Plano atual', current_author: 'Dr. Silva',
}
const file: ClinicalDocumentPublic = { ...note, id: 'file-1', kind: 'file', title: 'Relatório', current_version: 1, current_content: null }
const versions: ClinicalDocumentVersionPublic[] = [
  { id: 'v1', document_id: note.id, author_name: 'Dr. Silva', version: 1, content: 'Plano inicial', original_filename: null, media_type: null, file_size: null, created_at: '2026-10-01T10:00:00Z', is_current: false },
  { id: 'v2', document_id: note.id, author_name: 'Dr. Silva', version: 2, content: 'Plano atual', original_filename: null, media_type: null, file_size: null, created_at: '2026-10-02T10:00:00Z', is_current: true },
]

function renderSection(canWrite = false) {
  return render(<MemoryRouter><ClinicalDocumentsSection patientId="patient-1" canWrite={canWrite} /></MemoryRouter>)
}

describe('ClinicalDocumentsSection', () => {
  beforeEach(() => {
    state.documents = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    state.history = { data: versions, isLoading: false, isError: false, refetch: vi.fn() }
    state.create = { mutate: vi.fn(), isPending: false }
    state.update = { mutate: vi.fn(), isPending: false }
    state.upload = { mutate: vi.fn(), isPending: false }
    state.uploadVersion = { mutate: vi.fn(), isPending: false }
  })

  it('renders loading, error and empty states', async () => {
    state.documents.isLoading = true
    const { unmount } = renderSection()
    expect(screen.getByRole('status')).toHaveTextContent('A carregar')
    unmount()
    state.documents = { ...state.documents, isLoading: false, isError: true, error: new ApiError(503, 'erro'), data: undefined }
    renderSection()
    expect(screen.getByRole('alert')).toHaveTextContent('O serviço está temporariamente indisponível')
    unmount()
    state.documents = { ...state.documents, isError: false, error: null, data: [] }
    renderSection()
    expect(screen.getByText('Sem documentos')).toBeInTheDocument()
  })

  it('separates files and notes, displays versions and hides write actions from patients', async () => {
    state.documents.data = [file, note]
    const user = userEvent.setup()
    renderSection(false)
    expect(screen.getByRole('heading', { name: 'Ficheiros' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Notas' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar nota' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ver versões de Plano de cuidados' }))
    expect(await screen.findByText('Plano inicial')).toBeInTheDocument()
    expect(screen.getByText('Versão 2 · Atual')).toBeInTheDocument()
    expect(screen.getAllByText(/Dr. Silva/)).toHaveLength(4)
  })

  it('creates a note and uploads a PDF through separate accessible forms', async () => {
    const user = userEvent.setup()
    renderSection(true)
    await user.type(screen.getByLabelText('Título da nota'), 'Instruções')
    await user.type(screen.getByLabelText('Conteúdo'), 'Descansar')
    await user.click(screen.getByRole('button', { name: 'Guardar nota' }))
    expect(state.create.mutate).toHaveBeenCalledWith({ title: 'Instruções', content: 'Descansar' }, expect.objectContaining({ onSuccess: expect.any(Function) }))

    await user.type(screen.getByLabelText('Título do ficheiro'), 'Relatório')
    const pdf = new File(['%PDF-1.7'], 'relatorio.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Ficheiro PDF'), pdf)
    await user.click(screen.getByRole('button', { name: 'Carregar ficheiro' }))
    expect(state.upload.mutate).toHaveBeenCalledWith({ title: 'Relatório', file: pdf }, expect.objectContaining({ onSuccess: expect.any(Function) }))
  })

  it('offers download for files and starts a new note version for staff', async () => {
    state.documents.data = [file, note]
    const user = userEvent.setup()
    renderSection(true)
    expect(screen.getByRole('button', { name: 'Descarregar Relatório' })).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Nova versão' })[1])
    expect(screen.getByRole('heading', { name: 'Nova versão da nota' })).toBeInTheDocument()
  })
})
