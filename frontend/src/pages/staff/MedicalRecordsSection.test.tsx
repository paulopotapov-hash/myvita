import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { MedicalRecordPublic } from '../../types/api'
import { MedicalRecordsSection } from './MedicalRecordsSection'

const h = vi.hoisted(() => ({
  list: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  revisions: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useMedicalRecords: () => h.list,
  useMedicalRecordRevisions: () => h.revisions,
  useCreateMedicalRecord: () => h.create,
  useUpdateMedicalRecord: () => h.update,
}))

const record: MedicalRecordPublic = {
  id: 'rec-1',
  clinic_id: 'clinic-1',
  patient_id: 'patient-1',
  author_staff_id: 'staff-1',
  title: 'Avaliação',
  content: 'Evolução clínica',
  version: 2,
  created_at: '2026-09-24T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
}

describe('MedicalRecordsSection', () => {
  beforeEach(() => {
    h.list = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.revisions = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.create = { mutate: vi.fn(), isPending: false }
    h.update = { mutate: vi.fn(), isPending: false }
  })

  it('shows loading, retryable error and empty states', async () => {
    h.list.isLoading = true
    const { unmount } = render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    expect(screen.getByRole('status')).toHaveTextContent('A carregar')
    unmount()

    h.list = { ...h.list, isLoading: false, isError: true, error: new ApiError(500, 'x'), data: undefined }
    const user = userEvent.setup()
    const second = render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(h.list.refetch).toHaveBeenCalled()
    second.unmount()

    h.list = { ...h.list, isError: false, error: null, data: [] }
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    expect(screen.getByText('Sem registos clínicos')).toBeInTheDocument()
  })

  it('is read-only without write permission', () => {
    h.list.data = [record]
    render(<MedicalRecordsSection patientId="patient-1" canWrite={false} />)
    expect(screen.getByText('Avaliação')).toBeInTheDocument()
    expect(screen.queryByLabelText('Título do registo')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
  })

  it('requires title and content with field-level messages and no request', async () => {
    const user = userEvent.setup()
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.click(screen.getByRole('button', { name: 'Criar registo' }))
    expect(screen.getByText('Indica o título do registo.')).toBeInTheDocument()
    expect(screen.getByText('Indica o conteúdo clínico.')).toBeInTheDocument()
    expect(screen.getByLabelText('Título do registo')).toHaveAttribute('aria-invalid', 'true')
    expect(h.create.mutate).not.toHaveBeenCalled()
  })

  it('creates a trimmed record, confirms success and resets the form', async () => {
    const user = userEvent.setup()
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.type(screen.getByLabelText('Título do registo'), '  Consulta  ')
    await user.type(screen.getByLabelText('Conteúdo clínico'), 'Sem queixas')
    await user.click(screen.getByRole('button', { name: 'Criar registo' }))
    expect(h.create.mutate).toHaveBeenCalledWith(
      { title: 'Consulta', content: 'Sem queixas' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
    const options = h.create.mutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
    act(() => options.onSuccess())
    expect(await screen.findByRole('status')).toHaveTextContent('Registo clínico guardado.')
    expect(screen.getByLabelText('Título do registo')).toHaveValue('')
  })

  it('shows backend errors next to the field or as an alert', async () => {
    const user = userEvent.setup()
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.type(screen.getByLabelText('Título do registo'), 'T')
    await user.type(screen.getByLabelText('Conteúdo clínico'), 'C')
    await user.click(screen.getByRole('button', { name: 'Criar registo' }))
    const options = h.create.mutate.mock.calls.at(-1)?.[1] as { onError: (error: unknown) => void }
    act(() => options.onError(new ApiError(422, 'x', { fieldErrors: { content: 'Conteúdo inválido' } })))
    expect(await screen.findByText('Conteúdo inválido')).toBeInTheDocument()
    act(() => options.onError(new ApiError(403, 'x', { detail: 'Sem permissões clínicas.' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sem permissões clínicas.')
  })

  it('edits a record as a new version and lists its revisions', async () => {
    h.list.data = [record]
    h.revisions.data = [
      { id: 'r1', record_id: 'rec-1', editor_staff_id: 's', version: 1, title: 'a', content: 'b', created_at: '2026-09-24T10:00:00Z' },
    ]
    const user = userEvent.setup()
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.click(screen.getByRole('button', { name: 'Editar' }))
    expect(screen.getByLabelText('Título do registo')).toHaveValue('Avaliação')
    expect(screen.getByText('Revisões')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Conteúdo clínico'), ' revista')
    await user.click(screen.getByRole('button', { name: 'Guardar nova versão' }))
    expect(h.update.mutate).toHaveBeenCalledWith(
      { id: 'rec-1', payload: { title: 'Avaliação', content: 'Evolução clínica revista' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows a retryable error when revisions fail to load', async () => {
    h.list.data = [record]
    h.revisions = { ...h.revisions, isError: true, error: new ApiError(500, 'x'), data: undefined }
    const user = userEvent.setup()
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    await user.click(screen.getByRole('button', { name: 'Editar' }))
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(h.revisions.refetch).toHaveBeenCalled()
  })

  it('prevents double submit while saving', () => {
    h.update.isPending = true
    render(<MedicalRecordsSection patientId="patient-1" canWrite />)
    const button = screen.getByRole('button', { name: 'Criar registo' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })
})
