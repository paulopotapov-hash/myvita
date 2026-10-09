import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { MedicalRecordPublic, MedicalRecordRevisionPublic } from '../../types/api'
import { PatientDetailPage } from './PatientDetailPage'

// Coverage for the live (inline) medical-records section of PatientDetailPage.
// Replaces Parent A's tests of its standalone MedicalRecordsSection, which no
// route rendered after the merge (see _integration/replaced-tests.md).

const h = vi.hoisted(() => ({
  session: { role: 'staff' as 'staff' | 'patient', staff_role: 'doctor' as 'doctor' | null, patient_id: null as string | null },
  list: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  revisions: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
}))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ user: { id: 'user-1', email: 'u@example.com', full_name: 'Utilizador', clinic_id: 'clinic-1', ...h.session } }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  usePatient: () => ({
    data: { id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678', national_health_number: '123456789', is_active: true },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useUpdatePatient: () => ({ mutate: vi.fn(), isPending: false }),
  useAppointments: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useMedicalRecords: () => h.list,
  useMedicalRecordRevisions: () => h.revisions,
  useCreateMedicalRecord: () => h.create,
  useUpdateMedicalRecord: () => h.update,
  useMedications: () => ({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useDeactivateMedication: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../../hooks/useDocuments', () => ({
  usePatientDocuments: () => ({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
  useUploadDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useDownloadDocument: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../../hooks/useConsents', () => ({
  usePatientConsents: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useGrantConsent: () => ({ mutate: vi.fn(), isPending: false }),
  useRevokeConsent: () => ({ mutate: vi.fn(), isPending: false }),
}))

const record: MedicalRecordPublic = {
  id: 'rec-1',
  clinic_id: 'clinic-1',
  patient_id: 'patient-1',
  author_staff_id: 'staff-1',
  author_name: 'Dra. Rita Sousa',
  title: 'Avaliação',
  content: 'Evolução clínica',
  version: 2,
  created_at: '2026-09-24T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
}

const revision: MedicalRecordRevisionPublic = {
  id: 'rev-1',
  record_id: 'rec-1',
  editor_staff_id: 'staff-2',
  editor_name: 'Enf. João Lima',
  version: 1,
  title: 'Avaliação',
  content: 'Versão anterior',
  created_at: '2026-09-24T10:00:00Z',
}

type Options = { onSuccess?: () => void; onError?: (error: unknown) => void }

async function openRecords(user: ReturnType<typeof userEvent.setup>) {
  render(
    <MemoryRouter initialEntries={['/app/pacientes/patient-1']}>
      <Routes><Route path="/app/pacientes/:id" element={<PatientDetailPage />} /></Routes>
    </MemoryRouter>,
  )
  await user.click(screen.getByRole('tab', { name: 'Registos clínicos' }))
  return screen.getByRole('tabpanel')
}

describe('PatientDetailPage medical records (inline section)', () => {
  beforeEach(() => {
    h.session = { role: 'staff', staff_role: 'doctor', patient_id: null }
    h.list = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.revisions = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.create = { mutate: vi.fn(), isPending: false }
    h.update = { mutate: vi.fn(), isPending: false }
  })

  it('shows a retryable error state', async () => {
    const user = userEvent.setup()
    h.list = { data: undefined, isLoading: false, isError: true, error: new ApiError(500, 'x'), refetch: vi.fn() }
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: /tentar/i }))
    expect(h.list.refetch).toHaveBeenCalled()
  })

  it('shows the empty state', async () => {
    const user = userEvent.setup()
    const panel = await openRecords(user)
    expect(within(panel).getByText('Sem registos clínicos')).toBeInTheDocument()
  })

  it('is read-only for the patient: no form and no edit action', async () => {
    const user = userEvent.setup()
    h.session = { role: 'patient', staff_role: null, patient_id: 'patient-1' }
    h.list.data = [record]
    const panel = await openRecords(user)
    expect(within(panel).getByText('Evolução clínica')).toBeInTheDocument()
    expect(within(panel).queryByLabelText('Título do registo')).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
  })

  it('requires title and content and sends no request otherwise', async () => {
    const user = userEvent.setup()
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Criar registo' }))
    expect(within(panel).getByRole('alert')).toHaveTextContent('Preenche o título e o conteúdo clínico.')
    expect(h.create.mutate).not.toHaveBeenCalled()
  })

  it('creates a record, confirms success and resets the form', async () => {
    const user = userEvent.setup()
    const panel = await openRecords(user)
    await user.type(within(panel).getByLabelText('Título do registo'), 'Nota de consulta')
    await user.type(within(panel).getByLabelText('Conteúdo clínico'), 'Sem queixas.')
    await user.click(within(panel).getByRole('button', { name: 'Criar registo' }))
    expect(h.create.mutate).toHaveBeenCalledWith({ title: 'Nota de consulta', content: 'Sem queixas.' }, expect.any(Object))
    const options = h.create.mutate.mock.calls[0][1] as Options
    act(() => options.onSuccess?.())
    expect(within(panel).getByRole('status')).toHaveTextContent('Registo clínico guardado.')
    expect(within(panel).getByLabelText('Título do registo')).toHaveValue('')
  })

  it('edits a record as a new version with the optimistic-concurrency token and lists its revisions', async () => {
    const user = userEvent.setup()
    h.list.data = [record]
    h.revisions.data = [revision]
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Editar' }))
    expect(within(panel).getByText('Revisões')).toBeInTheDocument()
    expect(within(panel).getByText(/Versão 1/)).toBeInTheDocument()
    const content = within(panel).getByLabelText('Conteúdo clínico')
    await user.clear(content)
    await user.type(content, 'Evolução favorável')
    await user.click(within(panel).getByRole('button', { name: 'Guardar alterações' }))
    expect(h.update.mutate).toHaveBeenCalledWith(
      { id: 'rec-1', payload: { title: 'Avaliação', content: 'Evolução favorável', expected_version: 2 } },
      expect.any(Object),
    )
  })

  it('explains a concurrent edit (409) with the backend reason', async () => {
    const user = userEvent.setup()
    h.list.data = [record]
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Editar' }))
    await user.click(within(panel).getByRole('button', { name: 'Guardar alterações' }))
    const options = h.update.mutate.mock.calls[0][1] as Options
    act(() => options.onError?.(new ApiError(409, 'x', { detail: 'O registo foi alterado entretanto.' })))
    expect(within(panel).getByRole('alert')).toHaveTextContent('O registo foi alterado entretanto.')
  })

  it('shows a retryable error when revisions fail to load', async () => {
    const user = userEvent.setup()
    h.list.data = [record]
    h.revisions = { data: undefined, isLoading: false, isError: true, error: new ApiError(500, 'x'), refetch: vi.fn() }
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Editar' }))
    await user.click(within(panel).getByRole('button', { name: /tentar/i }))
    expect(h.revisions.refetch).toHaveBeenCalled()
  })

  it.each([
    ['staff', { role: 'staff' as const, staff_role: 'doctor' as const, patient_id: null }],
    ['patient', { role: 'patient' as const, staff_role: null, patient_id: 'patient-1' }],
  ])('shows author and editor display names, never internal staff ids, to %s', async (_label, session) => {
    const user = userEvent.setup()
    h.session = session
    h.list.data = [record]
    h.revisions.data = [revision]
    const panel = await openRecords(user)
    expect(within(panel).getByText(/Autor Dra\. Rita Sousa/)).toBeInTheDocument()
    expect(panel).not.toHaveTextContent('staff-1')
    if (session.role === 'staff') {
      await user.click(within(panel).getByRole('button', { name: 'Editar' }))
      expect(within(panel).getByText(/Autor Enf\. João Lima/)).toBeInTheDocument()
      expect(panel).not.toHaveTextContent('staff-2')
    }
  })

  it('prevents double submit while saving', async () => {
    const user = userEvent.setup()
    h.create.isPending = true
    const panel = await openRecords(user)
    expect(within(panel).getByRole('button', { name: /Criar registo/ })).toBeDisabled()
  })
})
