import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PatientProfilePage } from './PatientProfilePage'

const { patientState, refetch, updateMutate } = vi.hoisted(() => ({
  patientState: { data: null as Record<string, unknown> | null, isLoading: true, isError: false },
  refetch: vi.fn(),
  updateMutate: vi.fn(),
}))

vi.mock('../../components/patientPhoto/ProfilePhotoSection', () => ({ ProfilePhotoSection: () => null }))
vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ user: { id: 'u1', full_name: 'Ana Silva', email: 'ana@example.pt', role: 'patient', patient_id: 'p1' } }),
}))
vi.mock('../../components/PatientIdentifiersCard', () => ({
  PatientIdentifiersCard: ({ patientId }: { patientId: string }) => <p>Cartão de identificação {patientId}</p>,
}))
vi.mock('../../hooks/useOwnClinicName', () => ({ useOwnClinicName: () => 'Clínica Centro' }))
vi.mock('../../hooks/useClinicData', () => ({
  usePatient: (id: string) => {
    expect(id).toBe('p1')
    return { ...patientState, refetch }
  },
  useUpdatePatient: (id: string) => {
    expect(id).toBe('p1')
    return { mutate: updateMutate, isPending: false }
  },
}))

function renderPage() {
  const queryClient = new QueryClient()
  return render(<QueryClientProvider client={queryClient}><PatientProfilePage /></QueryClientProvider>)
}

describe('PatientProfilePage', () => {
  it('shows a loading state while fetching the backend-provided profile', () => {
    patientState.data = null
    patientState.isLoading = true
    patientState.isError = false
    renderPage()
    expect(screen.getByRole('status')).toHaveTextContent('A carregar dados do perfil')
    expect(screen.queryByText(/a API atual só os devolve/i)).not.toBeInTheDocument()
  })

  it('shows demographic fields from the patient endpoint when available', () => {
    patientState.data = {
      id: 'p1', clinic_id: 'c1', full_name: 'Ana Silva', birth_date: '1990-01-02',
      phone: '912345678', address: { street: null, postal_code: null, locality: null },
      identifiers: { nif: null, niss: null, national_health_number: null }, is_active: true,
    }
    patientState.isLoading = false
    patientState.isError = false
    renderPage()
    expect(screen.getByText('02/01/1990')).toBeInTheDocument()
    expect(screen.getByText('912345678')).toBeInTheDocument()
    expect(screen.queryByText(/não podem ser consultados/i)).not.toBeInTheDocument()
  })

  it('provides a retry action when the profile request fails', () => {
    patientState.data = null
    patientState.isLoading = false
    patientState.isError = true
    renderPage()
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível carregar os dados do perfil clínico.')
    screen.getByRole('button', { name: 'Tentar novamente' }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('shows personal data and the identifiers card, keeps the email read-only and lets the patient edit the phone', async () => {
    patientState.data = {
      id: 'p1', clinic_id: 'c1', full_name: 'Ana Silva', birth_date: '1990-01-02',
      phone: '912345678', address: { street: 'Rua Sintética, 1', postal_code: '1000-001', locality: 'Lisboa' },
      identifiers: { nif: '••••••789', niss: null, national_health_number: '••••••321' }, is_active: true,
    }
    patientState.isLoading = false
    patientState.isError = false
    updateMutate.mockReset()
    const user = userEvent.setup()
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'O meu perfil' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dados pessoais' })).toBeInTheDocument()
    expect(screen.getByText('Rua Sintética, 1, 1000-001 Lisboa')).toBeInTheDocument()
    expect(screen.getByText('Cartão de identificação p1')).toBeInTheDocument()
    expect(screen.getByText('ana@example.pt')).toBeInTheDocument()
    // The patient edits phone and address; the email has no edit action.
    expect(screen.getAllByRole('button', { name: /Editar/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      'Editar telefone',
      'Editar morada',
    ])

    await user.click(screen.getByRole('button', { name: 'Editar telefone' }))
    const field = screen.getByLabelText('Telefone')
    await user.clear(field)
    await user.type(field, ' 934567890 ')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(updateMutate).toHaveBeenCalledWith({ phone: '934567890' }, expect.objectContaining({ onSuccess: expect.any(Function) }))

    const options = updateMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => options.onSuccess())
    expect(screen.getByRole('status')).toHaveTextContent('Telefone atualizado.')
    expect(screen.queryByLabelText('Telefone')).not.toBeInTheDocument()
  })

  it('lets the patient edit the address and checks the postal code format first', async () => {
    patientState.data = {
      id: 'p1', clinic_id: 'c1', full_name: 'Ana Silva', birth_date: null, phone: null,
      address: { street: null, postal_code: null, locality: null },
      identifiers: { nif: null, niss: null, national_health_number: null }, is_active: true,
    }
    patientState.isLoading = false
    patientState.isError = false
    updateMutate.mockReset()
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Editar morada' }))
    await user.type(screen.getByLabelText('Rua'), 'Rua Sintética, 1')
    await user.type(screen.getByLabelText('Código postal'), '1000001')
    await user.type(screen.getByLabelText('Localidade'), 'Lisboa')
    await user.click(screen.getByRole('button', { name: 'Guardar morada' }))
    expect(screen.getByText('O código postal deve ter o formato 0000-000.')).toBeInTheDocument()
    expect(updateMutate).not.toHaveBeenCalled()

    await user.clear(screen.getByLabelText('Código postal'))
    await user.type(screen.getByLabelText('Código postal'), '1000-001')
    await user.click(screen.getByRole('button', { name: 'Guardar morada' }))
    expect(updateMutate).toHaveBeenCalledWith(
      { address_street: 'Rua Sintética, 1', address_postal_code: '1000-001', address_locality: 'Lisboa' },
      expect.any(Object),
    )
    const options = updateMutate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => options.onSuccess())
    expect(screen.getByRole('status')).toHaveTextContent('Morada atualizada.')
  })
})
