import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PatientDetailPage } from './PatientDetailPage'

const grantMutate = vi.fn()
const revokeMutate = vi.fn()

vi.mock('../../hooks/useClinicData', () => ({
  usePatients: () => ({
    data: [{ id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678' }],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAppointments: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
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
})
