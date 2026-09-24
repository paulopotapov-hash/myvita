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
  useMedications: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateMedication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateMedication: () => ({ mutate: vi.fn(), isPending: false }),
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

function renderOwnPage() {
  return render(
    <MemoryRouter initialEntries={['/app/saude']}>
      <Routes><Route path="/app/saude" element={<PatientDetailPage own />} /></Routes>
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

  it('shows patient data and immutable consent history', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ana Silva' })).toBeInTheDocument()
    expect(screen.getByText('Cuidados clínicos')).toBeInTheDocument()
    expect(screen.getByText('Concedido')).toBeInTheDocument()
  })

  it('grants and revokes using the real B5 payload shape', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Finalidade'), 'Partilha assistencial')
    await user.click(screen.getByRole('button', { name: 'Conceder' }))
    expect(grantMutate).toHaveBeenCalledWith(
      { consent_type: 'treatment', purpose: 'Partilha assistencial' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )

    await user.click(screen.getByRole('button', { name: 'Revogar' }))
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('histórico'))
    expect(revokeMutate).toHaveBeenCalledWith(
      'consent-1',
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('uses patient_id from the restored session for patient self-service', () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    renderOwnPage()
    expect(usePatient).toHaveBeenCalledWith('patient-1')
    expect(screen.getByRole('heading', { name: 'Ana Silva' })).toBeInTheDocument()
  })
})
