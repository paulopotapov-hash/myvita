import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePatient, useUpdatePatient } from '../../hooks/usePatientRecord'
import { ApiError, NetworkError } from '../../lib/apiClient'
import type { PatientPublic } from '../../types/api'
import { PatientRecordPage } from './PatientRecordPage'

vi.mock('../../hooks/usePatientRecord')

const patient: PatientPublic = {
  id: 'patient-1',
  clinic_id: 'clinic-1',
  full_name: 'Ana Martins',
  birth_date: '1990-04-12',
  phone: '910000000',
  national_health_number: '123456789',
  is_active: true,
  created_at: '2030-01-01T10:00:00Z',
  updated_at: '2030-05-20T10:00:00Z',
}

function query(data: PatientPublic | undefined, options: { loading?: boolean; error?: unknown } = {}) {
  return {
    data,
    isLoading: options.loading ?? false,
    isError: options.error !== undefined,
    error: options.error ?? null,
    refetch: vi.fn(),
  }
}

const updateMutation = { mutate: vi.fn(), isPending: false }

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(usePatient).mockReturnValue(query(patient) as unknown as ReturnType<typeof usePatient>)
  vi.mocked(useUpdatePatient).mockReturnValue(updateMutation as unknown as ReturnType<typeof useUpdatePatient>)
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/app/pacientes/patient-1']}>
      <Routes>
        <Route path="/app/pacientes" element={<div>Lista de pacientes</div>} />
        <Route path="/app/pacientes/:patientId" element={<PatientRecordPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PatientRecordPage', () => {
  it('renders actual patient data without exposing immutable identifiers', () => {
    const consoleSpy = vi.spyOn(console, 'log')
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ana Martins' })).toBeInTheDocument()
    expect(screen.getByText('910000000')).toBeInTheDocument()
    expect(screen.getByText('123456789')).toBeInTheDocument()
    expect(screen.queryByText('clinic-1')).not.toBeInTheDocument()
    expect(screen.queryByText('patient-1')).not.toBeInTheDocument()
    expect(consoleSpy).not.toHaveBeenCalled()
    consoleSpy.mockRestore()
  })

  it('renders loading and missing optional values safely', () => {
    vi.mocked(usePatient).mockReturnValue(query(undefined, { loading: true }) as unknown as ReturnType<typeof usePatient>)
    const view = renderPage()
    expect(screen.getByRole('status')).toHaveTextContent('A carregar ficha do paciente…')

    vi.mocked(usePatient).mockReturnValue(query({ ...patient, birth_date: null, phone: null, national_health_number: null, updated_at: undefined }) as unknown as ReturnType<typeof usePatient>)
    view.rerender(<MemoryRouter initialEntries={['/app/pacientes/patient-1']}><Routes><Route path="/app/pacientes/:patientId" element={<PatientRecordPage />} /></Routes></MemoryRouter>)
    expect(screen.getByText('Não indicada')).toBeInTheDocument()
    expect(screen.getAllByText('Não indicado')).toHaveLength(2)
    expect(screen.getByText('Não disponível')).toBeInTheDocument()
  })

  it.each([
    [403, 'Não tens permissão para consultar esta ficha de paciente.'],
    [404, 'Paciente não encontrado'],
    [401, 'Sessão inválida ou expirada. Inicia sessão novamente.'],
  ])('handles HTTP %i without showing patient data', (status, message) => {
    vi.mocked(usePatient).mockReturnValue(query(undefined, { error: new ApiError(status, 'error') }) as unknown as ReturnType<typeof usePatient>)
    renderPage()
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByText('Ana Martins')).not.toBeInTheDocument()
  })

  it('offers retry for network and server errors', async () => {
    const result = query(undefined, { error: new NetworkError() })
    vi.mocked(usePatient).mockReturnValue(result as unknown as ReturnType<typeof usePatient>)
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(result.refetch).toHaveBeenCalledOnce()
  })

  it('opens prefilled edit mode and cancel restores view mode', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Editar dados' }))
    expect(screen.getByLabelText('Nome completo')).toHaveValue('Ana Martins')
    expect(screen.getByLabelText('Telefone')).toHaveValue('910000000')
    expect(screen.queryByLabelText('ID do paciente')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('ID da clínica')).not.toBeInTheDocument()
    await user.clear(screen.getByLabelText('Nome completo'))
    await user.type(screen.getByLabelText('Nome completo'), 'Nome alterado')
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByDisplayValue('Nome alterado')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ana Martins' })).toBeInTheDocument()
  })

  it('validates fields and sends only editable B2 values', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Editar dados' }))
    await user.clear(screen.getByLabelText('Nome completo'))
    await user.type(screen.getByLabelText('Nome completo'), ' ')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByText('O nome deve ter pelo menos 2 caracteres.')).toBeInTheDocument()
    expect(updateMutation.mutate).not.toHaveBeenCalled()

    await user.clear(screen.getByLabelText('Nome completo'))
    await user.type(screen.getByLabelText('Nome completo'), 'Ana Silva')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(updateMutation.mutate).toHaveBeenCalledWith({
      patientId: 'patient-1',
      payload: {
        full_name: 'Ana Silva',
        birth_date: '1990-04-12',
        phone: '910000000',
        national_health_number: '123456789',
      },
    }, expect.any(Object))
  })

  it('keeps edited input visible after a failed save and displays field errors', async () => {
    updateMutation.mutate.mockImplementation((_variables, options) => {
      options.onError(new ApiError(422, 'validation', { fieldErrors: { phone: 'Telefone inválido.' } }))
    })
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Editar dados' }))
    const phone = screen.getByLabelText('Telefone')
    await user.clear(phone)
    await user.type(phone, '912345678')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(phone).toHaveValue('912345678')
    expect(screen.getByText('Telefone inválido.')).toBeInTheDocument()
    expect(screen.getByText('Verifica os dados introduzidos.')).toBeInTheDocument()
  })

  it('navigates back to the patient list', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('link', { name: '← Voltar aos pacientes' }))
    expect(screen.getByText('Lista de pacientes')).toBeInTheDocument()
  })
})
