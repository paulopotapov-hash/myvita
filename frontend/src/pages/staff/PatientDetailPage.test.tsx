import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PatientDetailPage } from './PatientDetailPage'

const { grantMutate, revokeMutate, sessionState, usePatient, usePatientIdentification } = vi.hoisted(() => ({
  grantMutate: vi.fn(),
  revokeMutate: vi.fn(),
  sessionState: { role: 'clinic_admin', staff_role: null as 'doctor' | 'nurse' | 'admin' | null, patient_id: null as string | null },
  usePatient: vi.fn(),
  usePatientIdentification: vi.fn(),
}))

vi.mock('../../components/clinicalHistory/ClinicalHistorySection', () => ({
  ClinicalHistorySection: ({ patientId, mode }: { patientId: string; mode: string }) => <p>Histórico clínico {mode} {patientId}</p>,
}))

vi.mock('../../components/PatientIdentifiersCard', () => ({
  PatientIdentifiersCard: ({ patientId }: { patientId: string }) => <p>Cartão de identificação {patientId}</p>,
}))

vi.mock('../../hooks/useClinicData', () => ({
  usePatient: (id: string) => {
    usePatient(id)
    return {
    data: { id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678', address: { street: 'Rua Sintética, 1', postal_code: '1000-001', locality: 'Lisboa' }, identifiers: { nif: '••••••789', niss: null, national_health_number: '••••••321' }, is_active: true },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    }
  },
  usePatientIdentification: (id: string) => {
    usePatientIdentification(id)
    return {
      data: { id: 'patient-1', full_name: 'Ana Silva', identifiers: { nif: '••••••789', niss: null, national_health_number: null }, can_edit: true },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }
  },
  useUpdatePatient: () => ({ mutate: vi.fn(), isPending: false }),
  useAppointments: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
}))

vi.mock('../../hooks/usePatientPhoto', () => ({
  usePatientPhoto: () => ({ data: { approved: null, pending: null, can_review: false } }),
  usePhotoDecision: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'user-1', email: 'admin@example.com', full_name: 'Admin', clinic_id: 'clinic-1', ...sessionState },
  }),
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useMedicalRecords: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useMedicalRecordRevisions: () => ({ data: [], isLoading: false }),
  useCreateMedicalRecord: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedicalRecord: () => ({ mutate: vi.fn(), isPending: false }),
  useMedications: () => ({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useDeactivateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useMedicationAction: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../../hooks/useDocuments', () => ({
  usePatientDocuments: () => ({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
  useUploadDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useDownloadDocument: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../../hooks/useConsents', () => ({
  usePatientConsents: () => ({
    data: [{
      id: 'consent-1', clinic_id: 'clinic-1', patient_id: 'patient-1', consent_type: 'treatment',
      purpose: 'Cuidados clínicos', status: 'granted', granted_at: '2026-09-24T10:00:00Z',
      revoked_at: null, recorded_by_user_id: 'user-1', created_at: '2026-09-24T10:00:00Z',
      updated_at: '2026-09-24T10:00:00Z',
    }],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useGrantConsent: () => ({ mutate: grantMutate, isPending: false }),
  useRevokeConsent: () => ({ mutate: revokeMutate, isPending: false }),
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/app/pacientes/patient-1']}>
      <Routes><Route path="/app/pacientes/:id" element={<PatientDetailPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('PatientDetailPage consent workflow', () => {
  beforeEach(() => {
    grantMutate.mockReset()
    revokeMutate.mockReset()
    usePatient.mockReset()
    usePatientIdentification.mockReset()
    sessionState.role = 'staff'
    sessionState.staff_role = 'doctor'
    sessionState.patient_id = null
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows patient data and immutable consent history', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ana Silva' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Consentimentos' }))
    expect(screen.getByText('Cuidados clínicos')).toBeInTheDocument()
    expect(screen.getByText('Concedido')).toBeInTheDocument()
  })

  it('shows staff the consent history without the patient-only grant form', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(usePatient).toHaveBeenCalledWith('patient-1')
    await user.click(screen.getByRole('tab', { name: 'Consentimentos' }))
    expect(screen.queryByLabelText('Finalidade')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revogar' })).not.toBeInTheDocument()
  })

  it('keeps the tabbed file for doctors and nurses, with address and identifiers in Dados pessoais', () => {
    renderPage()
    expect(screen.getByRole('tab', { name: 'Dados pessoais', selected: true })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Registos clínicos' })).toBeInTheDocument()
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('Rua Sintética, 1, 1000-001 Lisboa')
    expect(panel).toHaveTextContent('Cartão de identificação patient-1')
    expect(screen.getByLabelText('Código postal')).toHaveValue('1000-001')
    // Identifiers are edited in their own card, never in this form.
    expect(screen.queryByLabelText('Número de utente')).not.toBeInTheDocument()
  })

  it('gives doctors and nurses a "Histórico" tab with the staff view of the clinical history', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('tab', { name: 'Histórico' }))
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('Histórico clínico staff patient-1')
    // The medication, declared or prescribed, is managed in its own tab.
    await user.click(within(panel).getByRole('button', { name: 'Medicamentos' }))
    expect(screen.getByRole('tab', { name: 'Medicamentos', selected: true })).toBeInTheDocument()
  })
})

describe('PatientDetailPage for administrative roles', () => {
  beforeEach(() => {
    usePatient.mockReset()
    usePatientIdentification.mockReset()
    sessionState.patient_id = null
  })

  it.each([
    ['the clinic administrator', 'clinic_admin', null],
    ['administrative staff', 'staff', 'admin'],
  ] as const)('gives %s only the identification card, never the clinical file', (_label, role, staffRole) => {
    sessionState.role = role
    sessionState.staff_role = staffRole
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Ana Silva' })).toBeInTheDocument()
    expect(screen.getByText('Cartão de identificação patient-1')).toBeInTheDocument()
    expect(usePatientIdentification).toHaveBeenCalledWith('patient-1')
    expect(usePatient).not.toHaveBeenCalled()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Documentos' })).not.toBeInTheDocument()
  })
})

describe('PatientDetailPage documents tab', () => {
  beforeEach(() => {
    sessionState.patient_id = null
  })

  it('lets a doctor open the patient documents with upload controls and the patient name', async () => {
    sessionState.role = 'staff'
    sessionState.staff_role = 'doctor'
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('tab', { name: 'Documentos' }))
    expect(screen.getByRole('heading', { name: 'Documentos' })).toBeInTheDocument()
    expect(screen.getByText('Documentos de Ana Silva')).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Carregar documento' })).toBeInTheDocument()
  })
})
