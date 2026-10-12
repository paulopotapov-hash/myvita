import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { MedicalRecordPatientView, MedicalRecordPublic, MedicalRecordRevisionPublic } from '../../types/api'
import { MedicalRecordsSection } from '../../components/MedicalRecordsSection'
import { PatientDetailPage } from './PatientDetailPage'

// Coverage for the medical-records section: inside the staff patient file
// (Registos clínicos tab) and, read-only, on the patient's "Resumo de saúde"
// page (/patient/saude), which renders the same MedicalRecordsSection.

const h = vi.hoisted(() => ({
  session: { role: 'staff' as 'staff' | 'patient', staff_role: 'doctor' as 'doctor' | null, patient_id: null as string | null },
  list: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  revisions: { data: [] as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
  visibility: { mutate: vi.fn(), isPending: false },
  single: { data: undefined as unknown, isLoading: false, isError: false, error: null as unknown },
  singleRequested: [] as Array<string | null>,
}))

vi.mock('../../hooks/usePatientPhoto', () => ({
  usePatientPhoto: () => ({ data: { approved: null, pending: null, can_review: false } }),
  usePhotoDecision: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ user: { id: 'user-1', email: 'u@example.com', full_name: 'Utilizador', clinic_id: 'clinic-1', ...h.session } }),
}))

vi.mock('../../components/PatientIdentifiersCard', () => ({ PatientIdentifiersCard: () => null }))

vi.mock('../../hooks/useClinicData', () => ({
  usePatient: () => ({
    data: { id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678', address: { street: 'Rua Sintética, 1', postal_code: '1000-001', locality: 'Lisboa' }, identifiers: { nif: '••••••789', niss: null, national_health_number: '••••••321' }, is_active: true },
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
  useChangeRecordVisibility: () => h.visibility,
  useMedicalRecord: (id: string | null) => { h.singleRequested.push(id); return id ? h.single : { data: undefined, isLoading: false, isError: false, error: null } },
  useMedications: () => ({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useDeactivateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useMedicationAction: () => ({ mutate: vi.fn(), isPending: false }),
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
  view: 'staff',
  id: 'rec-1',
  clinic_id: 'clinic-1',
  patient_id: 'patient-1',
  author_staff_id: 'staff-1',
  author_name: 'Dra. Rita Sousa',
  title: 'Avaliação',
  content: 'Evolução clínica',
  visibility: 'internal',
  visibility_changed_at: null,
  visibility_changed_by_name: null,
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
  visibility: 'internal',
  created_at: '2026-09-24T10:00:00Z',
}

/** What the backend sends a patient: shared records only, without staff ids or versions (P2.5). */
const patientRecord: MedicalRecordPatientView = {
  view: 'patient',
  id: 'rec-1',
  author_name: 'Dra. Rita Sousa',
  title: 'Avaliação',
  content: 'Evolução clínica',
  created_at: '2026-09-24T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
}

type Options = { onSuccess?: () => void; onError?: (error: unknown) => void }

async function openRecords(user: ReturnType<typeof userEvent.setup>) {
  if (h.session.role === 'patient') {
    // The patient reads shared records on their own health summary page, never in the staff file.
    render(<MemoryRouter initialEntries={['/patient/saude']}><MedicalRecordsSection patientId="patient-1" canWrite={false} /></MemoryRouter>)
    return screen.getByRole('heading', { name: 'Registos clínicos' }).closest('section') as HTMLElement
  }
  render(
    <MemoryRouter initialEntries={['/app/pacientes/patient-1']}>
      <Routes><Route path="/app/pacientes/:id" element={<PatientDetailPage />} /></Routes>
    </MemoryRouter>,
  )
  await user.click(screen.getByRole('tab', { name: 'Registos clínicos' }))
  return screen.getByRole('tabpanel')
}

describe('Medical records section (staff file and patient health summary)', () => {
  beforeEach(() => {
    h.session = { role: 'staff', staff_role: 'doctor', patient_id: null }
    h.list = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.revisions = { data: [], isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.create = { mutate: vi.fn(), isPending: false }
    h.update = { mutate: vi.fn(), isPending: false }
    h.visibility = { mutate: vi.fn(), isPending: false }
    h.single = { data: undefined, isLoading: false, isError: false, error: null }
    h.singleRequested = []
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
    h.list.data = [patientRecord]
    const panel = await openRecords(user)
    expect(within(panel).getByText('Evolução clínica')).toBeInTheDocument()
    expect(within(panel).queryByLabelText('Título do registo')).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
    // No staff-only workflow details in the patient view.
    expect(panel).not.toHaveTextContent('Versão')
    expect(panel).not.toHaveTextContent('Nota interna')
    expect(panel).not.toHaveTextContent('Partilhado com o paciente')
  })

  it('tells the patient when nothing has been shared yet', async () => {
    const user = userEvent.setup()
    h.session = { role: 'patient', staff_role: null, patient_id: 'patient-1' }
    const panel = await openRecords(user)
    expect(within(panel).getByText('A tua equipa clínica ainda não partilhou registos contigo.')).toBeInTheDocument()
  })

  it('labels internal, shared and legacy records for the care team', async () => {
    const user = userEvent.setup()
    h.list.data = [
      record,
      { ...record, id: 'rec-2', title: 'Plano', visibility: 'shared', visibility_changed_at: '2026-09-26T10:00:00Z', visibility_changed_by_name: 'Enf. João Lima' },
      { ...record, id: 'rec-3', title: 'Antigo', visibility: 'legacy_shared' },
    ]
    const panel = await openRecords(user)
    expect(within(panel).getByText('Nota interna')).toBeInTheDocument()
    expect(within(panel).getByText('Partilhado com o paciente')).toBeInTheDocument()
    expect(within(panel).getByText(/Partilhado por Enf\. João Lima/)).toBeInTheDocument()
    // Legacy access is shown as such, never as somebody's sharing decision.
    expect(within(panel).getByText(/anterior à partilha explícita/)).toBeInTheDocument()
    expect(within(panel).getAllByRole('button', { name: 'Partilhar com o paciente' })).toHaveLength(1)
    expect(within(panel).getAllByRole('button', { name: 'Confirmar partilha' })).toHaveLength(1)
    expect(within(panel).getAllByRole('button', { name: 'Deixar de partilhar' })).toHaveLength(2)
  })

  it('shares the reviewed version only after confirmation and reports a stale version', async () => {
    const user = userEvent.setup()
    h.list.data = [record]
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Partilhar com o paciente' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('versão 2')
    expect(dialog).toHaveTextContent('notificação genérica')
    await user.click(within(dialog).getByRole('button', { name: 'Partilhar' }))
    expect(h.visibility.mutate).toHaveBeenCalledWith({ id: 'rec-1', share: true, expectedVersion: 2 }, expect.any(Object))
    const options = h.visibility.mutate.mock.calls[0][1] as Options
    act(() => options.onError?.(new ApiError(409, 'x', { detail: 'conflict' })))
    expect(within(panel).getByRole('alert')).toHaveTextContent('Revê a versão atual antes de o partilhar.')
  })

  it('unshares after confirming that access ends immediately', async () => {
    const user = userEvent.setup()
    h.list.data = [{ ...record, visibility: 'shared', visibility_changed_at: '2026-09-26T10:00:00Z', visibility_changed_by_name: 'Dra. Rita Sousa' }]
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Deixar de partilhar' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('mesmo a partir de notificações antigas')
    await user.click(within(dialog).getByRole('button', { name: 'Deixar de partilhar' }))
    expect(h.visibility.mutate).toHaveBeenCalledWith({ id: 'rec-1', share: false, expectedVersion: 2 }, expect.any(Object))
    const options = h.visibility.mutate.mock.calls[0][1] as Options
    act(() => options.onSuccess?.())
    expect(within(panel).getByRole('status')).toHaveTextContent('O paciente deixou de ter acesso a este registo.')
  })

  it('shares a new record with the patient only when explicitly asked', async () => {
    const user = userEvent.setup()
    const panel = await openRecords(user)
    const share = within(panel).getByRole('checkbox', { name: /Partilhar com o paciente/ })
    expect(share).not.toBeChecked()
    await user.type(within(panel).getByLabelText('Título do registo'), 'Plano')
    await user.type(within(panel).getByLabelText('Conteúdo clínico'), 'Repouso.')
    await user.click(share)
    await user.click(within(panel).getByRole('button', { name: 'Criar registo' }))
    expect(h.create.mutate).toHaveBeenCalledWith({ title: 'Plano', content: 'Repouso.', share_with_patient: true }, expect.any(Object))
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
    // Internal by default (P2.5).
    expect(h.create.mutate).toHaveBeenCalledWith({ title: 'Nota de consulta', content: 'Sem queixas.', share_with_patient: false }, expect.any(Object))
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

  it('never changes visibility from the edit form and warns when the patient sees the edit', async () => {
    const user = userEvent.setup()
    h.list.data = [{ ...record, visibility: 'shared', visibility_changed_at: '2026-09-26T10:00:00Z', visibility_changed_by_name: 'Dra. Rita Sousa' }]
    const panel = await openRecords(user)
    await user.click(within(panel).getByRole('button', { name: 'Editar' }))
    expect(within(panel).queryByRole('checkbox', { name: /Partilhar com o paciente/ })).not.toBeInTheDocument()
    expect(within(panel).getByRole('note')).toHaveTextContent('as alterações que guardares ficam visíveis de imediato')
    await user.click(within(panel).getByRole('button', { name: 'Guardar alterações' }))
    expect(h.update.mutate).toHaveBeenCalledWith(
      { id: 'rec-1', payload: { title: 'Avaliação', content: 'Evolução clínica', expected_version: 2 } },
      expect.any(Object),
    )
  })

  it('highlights a record opened from a notification, for the patient', () => {
    h.session = { role: 'patient', staff_role: null, patient_id: 'patient-1' }
    h.list.data = [patientRecord]
    render(
      <MemoryRouter initialEntries={['/patient/saude?record=rec-1']}>
        <Routes><Route path="/patient/saude" element={<MedicalRecordsSection patientId="patient-1" canWrite={false} />} /></Routes>
      </MemoryRouter>,
    )
    const row = screen.getByText('Evolução clínica').closest('li') as HTMLElement
    expect(row).toHaveAttribute('aria-current', 'true')
    expect(h.singleRequested.every((id) => id === null)).toBe(true)
    expect(screen.queryByRole('button', { name: /partilhar/i })).not.toBeInTheDocument()
  })

  it('tells the patient when a linked record is no longer available (unshared or never shared)', () => {
    h.session = { role: 'patient', staff_role: null, patient_id: 'patient-1' }
    h.list.data = []
    h.single = { data: undefined, isLoading: false, isError: true, error: new ApiError(404, 'x') }
    render(
      <MemoryRouter initialEntries={['/patient/saude?record=rec-9']}>
        <Routes><Route path="/patient/saude" element={<MedicalRecordsSection patientId="patient-1" canWrite={false} />} /></Routes>
      </MemoryRouter>,
    )
    expect(h.singleRequested).toContain('rec-9')
    expect(screen.getByRole('alert')).toHaveTextContent('Este registo não está disponível.')
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
    h.list.data = [session.role === 'patient' ? patientRecord : record]
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
