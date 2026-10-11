import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PatientDetailPage } from './PatientDetailPage'

const { grantMutate, revokeMutate, sessionState, usePatient } = vi.hoisted(() => ({
  grantMutate: vi.fn(),
  revokeMutate: vi.fn(),
  sessionState: { role: 'clinic_admin', staff_role: null as 'doctor' | 'nurse' | 'admin' | null, patient_id: null as string | null },
  usePatient: vi.fn(),
}))

vi.mock('../../hooks/useClinicData', () => ({
  usePatient: (id: string) => {
    usePatient(id)
    return {
    data: { id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678', national_health_number: '123456789', is_active: true },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    }
  },
  useUpdatePatient: () => ({ mutate: vi.fn(), isPending: false }),
  useAppointments: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
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
    sessionState.role = 'clinic_admin'
    sessionState.staff_role = null
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

  it('keeps the tabbed file for staff, starting on Dados pessoais', () => {
    sessionState.role = 'staff'
    sessionState.staff_role = 'doctor'
    renderPage()
    expect(screen.getByRole('tab', { name: 'Dados pessoais', selected: true })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Registos clínicos' })).toBeInTheDocument()
    expect(screen.getByLabelText('Número de utente')).toBeInTheDocument()
  })
})

describe('PatientDetailPage documents tab', () => {
  beforeEach(() => {
    sessionState.role = 'clinic_admin'
    sessionState.staff_role = null
    sessionState.patient_id = null
  })

  it('hides Documentos from clinic_admin, who has no clinical access in the backend', () => {
    renderPage()
    expect(screen.queryByRole('tab', { name: 'Documentos' })).not.toBeInTheDocument()
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
