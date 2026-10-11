import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HealthSummaryPage } from './HealthSummaryPage'
import { PatientConsentsPage } from './PatientConsentsPage'
import { PatientDocumentsPage } from './PatientDocumentsPage'
import { PatientMedicationPage } from './PatientMedicationPage'

// One page per section of the patient area: each page has its own title and
// shows only the patient's own data, without the staff-only controls.

const h = vi.hoisted(() => ({
  session: { role: 'patient', staff_role: null, patient_id: 'patient-1' as string | null },
  grantMutate: vi.fn(),
  revokeMutate: vi.fn(),
  requested: [] as string[],
  appointments: [] as unknown[],
  medications: [] as unknown[],
  results: [] as unknown[],
}))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ user: { id: 'user-1', email: 'ana@example.pt', full_name: 'Ana Silva', clinic_id: 'clinic-1', ...h.session } }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  useAppointments: () => ({ data: h.appointments, isLoading: false, isError: false, refetch: vi.fn() }),
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useMedications: (patientId: string) => {
    h.requested.push(`medications:${patientId}`)
    return { data: { items: h.medications, total: h.medications.length }, isLoading: false, isError: false, refetch: vi.fn() }
  },
  useCreateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useDeactivateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useMedicalRecords: (patientId: string) => {
    h.requested.push(`records:${patientId}`)
    return { data: [], isLoading: false, isError: false, refetch: vi.fn() }
  },
  useMedicalRecordRevisions: () => ({ data: [], isLoading: false }),
  useCreateMedicalRecord: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedicalRecord: () => ({ mutate: vi.fn(), isPending: false }),
  useChangeRecordVisibility: () => ({ mutate: vi.fn(), isPending: false }),
  useMedicalRecord: () => ({ data: undefined, isLoading: false, isError: false, error: null }),
}))

vi.mock('../../hooks/useClinicalResults', () => ({
  useClinicalResults: () => ({ data: { items: h.results, total: h.results.length }, isLoading: false, isError: false, refetch: vi.fn() }),
}))

vi.mock('../../hooks/useDocuments', () => ({
  usePatientDocuments: (patientId: string) => {
    h.requested.push(`documents:${patientId}`)
    return { data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }
  },
  useUploadDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useDownloadDocument: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../../hooks/useConsents', () => ({
  usePatientConsents: (patientId: string) => {
    h.requested.push(`consents:${patientId}`)
    return {
      data: [{
        view: 'patient', id: 'consent-1', consent_type: 'treatment', purpose: 'Cuidados clínicos', status: 'granted',
        granted_at: '2026-09-24T10:00:00Z', revoked_at: null, created_at: '2026-09-24T10:00:00Z', updated_at: '2026-09-24T10:00:00Z',
      }],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }
  },
  useGrantConsent: () => ({ mutate: h.grantMutate, isPending: false }),
  useRevokeConsent: () => ({ mutate: h.revokeMutate, isPending: false }),
}))

function renderAt(element: React.ReactElement, path = '/patient') {
  return render(<MemoryRouter initialEntries={[path]}>{element}</MemoryRouter>)
}

const medication = (id: string, name: string, status: 'active' | 'completed') => ({
  view: 'patient', id, name, dosage: '500 mg', route: null, frequency: '8/8h', instructions: null, status,
  start_date: '2026-09-01', end_date: status === 'active' ? null : '2026-09-10', created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
})

beforeEach(() => {
  h.session = { role: 'patient', staff_role: null, patient_id: 'patient-1' }
  h.grantMutate.mockReset()
  h.revokeMutate.mockReset()
  h.requested = []
  h.appointments = []
  h.medications = []
  h.results = []
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('Os meus consentimentos', () => {
  it('lets the patient grant and revoke their own consents (real payload shape)', async () => {
    const user = userEvent.setup()
    renderAt(<PatientConsentsPage />, '/patient/consentimentos')
    expect(screen.getByRole('heading', { level: 1, name: 'Os meus consentimentos' })).toBeInTheDocument()
    expect(h.requested).toContain('consents:patient-1')

    await user.type(screen.getByLabelText('Finalidade'), 'Partilha assistencial')
    await user.click(screen.getByRole('button', { name: 'Conceder' }))
    expect(h.grantMutate).toHaveBeenCalledWith(
      { consent_type: 'treatment', purpose: 'Partilha assistencial' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )

    await user.click(screen.getByRole('button', { name: 'Revogar' }))
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('histórico'))
    expect(h.revokeMutate).toHaveBeenCalledWith('consent-1', expect.objectContaining({ onSuccess: expect.any(Function) }))
  })

  it('shows an error instead of content when the session has no patient identity', () => {
    h.session = { role: 'patient', staff_role: null, patient_id: null }
    renderAt(<PatientConsentsPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Os meus consentimentos' })).toBeInTheDocument()
    expect(screen.getByText('A sessão não contém uma identidade de paciente válida.')).toBeInTheDocument()
    expect(h.requested).toEqual([])
  })
})

describe('Os meus documentos', () => {
  it('lists the patient documents without upload controls or tabs', () => {
    renderAt(<PatientDocumentsPage />, '/patient/documentos')
    expect(screen.getByRole('heading', { level: 1, name: 'Os meus documentos' })).toBeInTheDocument()
    expect(h.requested).toContain('documents:patient-1')
    expect(screen.queryByRole('form', { name: 'Carregar documento' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })
})

describe('A minha medicação', () => {
  it('is read-only for the patient', () => {
    h.medications = [medication('m1', 'Paracetamol', 'active')]
    renderAt(<PatientMedicationPage />, '/patient/medicacao')
    expect(screen.getByRole('heading', { level: 1, name: 'A minha medicação' })).toBeInTheDocument()
    expect(screen.getByText(/Paracetamol/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Medicamento')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
  })
})

describe('Resumo de saúde', () => {
  it('summarises current medication, the next appointment and the latest results, then the shared records', () => {
    h.medications = [medication('m1', 'Paracetamol', 'active'), medication('m2', 'Amoxicilina', 'completed')]
    h.appointments = [
      { view: 'patient', id: 'a-past', staff_name: 'Dra. Rita Sousa', scheduled_at: '2020-01-01T10:00:00Z', duration_minutes: 30, status: 'scheduled', reason: null },
      { view: 'patient', id: 'a-next', staff_name: 'Dra. Rita Sousa', scheduled_at: '2099-01-01T10:00:00Z', duration_minutes: 30, status: 'confirmed', reason: null },
    ]
    h.results = [{
      view: 'patient', id: 'r1', category: 'laboratory', title: 'Hemograma', value: null, unit: null, reference_range: null, summary: null,
      result_date: '2026-09-20', document_id: null, author_name: 'Dra. Rita Sousa', released_at: '2026-09-21T10:00:00Z',
      corrects_result_id: null, superseded_by_result_id: null,
    }]
    renderAt(<HealthSummaryPage />, '/patient/saude')

    expect(screen.getByRole('heading', { level: 1, name: 'Resumo de saúde' })).toBeInTheDocument()
    const medicationCard = screen.getByRole('region', { name: 'Medicação atual' })
    expect(within(medicationCard).getByText('Paracetamol')).toBeInTheDocument()
    expect(medicationCard).not.toHaveTextContent('Amoxicilina')

    const appointmentCard = screen.getByRole('region', { name: 'Próxima consulta' })
    expect(within(appointmentCard).getByRole('link', { name: 'Ver detalhes' })).toHaveAttribute('href', '/patient/consultas?consulta=a-next')

    const resultsCard = screen.getByRole('region', { name: 'Últimos resultados' })
    expect(within(resultsCard).getByRole('link', { name: 'Hemograma' })).toHaveAttribute('href', '/patient/resultados?result=r1')

    expect(screen.getByRole('heading', { name: 'Registos clínicos' })).toBeInTheDocument()
    expect(h.requested).toContain('records:patient-1')
    expect(screen.queryByLabelText('Título do registo')).not.toBeInTheDocument()
  })

  it('says so when there is nothing to summarise', () => {
    renderAt(<HealthSummaryPage />, '/patient/saude')
    expect(screen.getByText('Sem medicação ativa.')).toBeInTheDocument()
    expect(screen.getByText('Sem consultas marcadas.')).toBeInTheDocument()
    expect(screen.getByText('Sem resultados disponíveis.')).toBeInTheDocument()
  })
})
