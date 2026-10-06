import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { PatientDetailPage } from './PatientDetailPage'

const { consentPending, grantMutate, revokeMutate, sessionState, updateMutate, usePatient } = vi.hoisted(() => ({
  consentPending: { grant: false, revoke: false },
  grantMutate: vi.fn(),
  revokeMutate: vi.fn(),
  updateMutate: vi.fn(),
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
  useUpdatePatient: () => ({ mutate: updateMutate, isPending: false }),
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
  useGrantConsent: () => ({ mutate: grantMutate, isPending: consentPending.grant }),
  useRevokeConsent: () => ({ mutate: revokeMutate, isPending: consentPending.revoke, variables: undefined }),
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
    updateMutate.mockReset()
    consentPending.grant = consentPending.revoke = false
    usePatient.mockReset()
    sessionState.role = 'clinic_admin'
    sessionState.staff_role = null
    sessionState.patient_id = null
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows patient data and immutable consent history to clinical staff', () => {
    sessionState.role = 'staff'
    sessionState.staff_role = 'nurse'
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ana Silva' })).toBeInTheDocument()
    expect(screen.getByText('Cuidados clínicos')).toBeInTheDocument()
    expect(screen.getByText('Concedido')).toBeInTheDocument()
  })

  it('does not offer consents to administrative roles, which the backend refuses', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ana Silva' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Consentimentos' })).not.toBeInTheDocument()
  })

  it('grants and revokes using the real B5 payload shape', async () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
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

  it('requires a consent purpose before calling the API', async () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Conceder' }))
    expect(screen.getByText('Indica a finalidade do consentimento.')).toBeInTheDocument()
    expect(screen.getByLabelText('Finalidade')).toHaveAttribute('aria-invalid', 'true')
    expect(grantMutate).not.toHaveBeenCalled()
  })

  it('confirms a granted consent, clears the field and reports a revoke failure', async () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Finalidade'), 'Partilha assistencial')
    await user.click(screen.getByRole('button', { name: 'Conceder' }))
    const grantOptions = grantMutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void; onError: (e: unknown) => void }
    act(() => grantOptions.onError(new ApiError(409, 'x', { detail: 'Consentimento já concedido.' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('Consentimento já concedido.')
    act(() => grantOptions.onSuccess())
    expect(await screen.findByRole('status')).toHaveTextContent('Consentimento concedido')
    expect(screen.getByLabelText('Finalidade')).toHaveValue('')

    await user.click(screen.getByRole('button', { name: 'Revogar' }))
    const revokeOptions = revokeMutate.mock.calls.at(-1)?.[1] as { onError: (e: unknown) => void }
    act(() => revokeOptions.onError(new ApiError(409, 'x', { detail: 'Consentimento já revogado.' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('Consentimento já revogado.')
  })

  it('does not revoke when the confirmation is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Revogar' }))
    expect(revokeMutate).not.toHaveBeenCalled()
  })

  it('disables grant and revoke while either request is pending', () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    consentPending.revoke = true
    renderPage()
    expect(screen.getByRole('button', { name: 'Conceder' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Revogar' })).toBeDisabled()
  })

  it('validates patient contact fields before saving and confirms success', async () => {
    sessionState.role = 'staff'
    sessionState.staff_role = 'doctor'
    const user = userEvent.setup()
    renderPage()
    const phone = screen.getByLabelText('Telefone')
    fireEvent.change(phone, { target: { value: '9'.repeat(31) } })
    await user.click(screen.getByRole('button', { name: 'Guardar dados' }))
    expect(screen.getByText('O telefone pode ter no máximo 30 caracteres.')).toBeInTheDocument()
    expect(updateMutate).not.toHaveBeenCalled()

    await user.clear(phone)
    await user.type(phone, '911111111')
    await user.click(screen.getByRole('button', { name: 'Guardar dados' }))
    expect(updateMutate).toHaveBeenCalledWith(
      { phone: '911111111', national_health_number: '123456789' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
    const options = updateMutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void; onError: (e: unknown) => void }
    act(() => options.onError(new ApiError(403, 'x', { detail: 'Sem permissões.' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sem permissões.')
    act(() => options.onSuccess())
    expect(await screen.findByRole('status')).toHaveTextContent('Dados atualizados com sucesso.')
  })

  it('lets patients edit only their phone and sends nothing else', async () => {
    sessionState.role = 'patient'
    sessionState.patient_id = 'patient-1'
    const user = userEvent.setup()
    renderPage()
    expect(screen.queryByLabelText('Número de utente')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Guardar dados' }))
    expect(updateMutate).toHaveBeenCalledWith({ phone: '912345678' }, expect.anything())
  })
})
