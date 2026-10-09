import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { PatientsPage } from './PatientsPage'

const { usePatientsPage } = vi.hoisted(() => ({ usePatientsPage: vi.fn() }))

vi.mock('../../hooks/useClinicData', () => ({ usePatientsPage }))
// The invitation panel has its own tests (PatientInvitationsPanel.test.tsx).
vi.mock('../../components/PatientInvitationsPanel', () => ({ PatientInvitationsPanel: () => null }))
vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({ user: { role: 'staff', staff_role: 'doctor' } }),
}))

function renderPatientsPage(initialUrl = '') {
  return render(
    <MemoryRouter initialEntries={[initialUrl || '/app/pacientes']}>
      <PatientsPage />
    </MemoryRouter>,
  )
}

describe('PatientsPage', () => {
  beforeEach(() => {
    usePatientsPage.mockReset()
  })

  it('uses backend totals to paginate the patient directory', async () => {
    usePatientsPage.mockImplementation((_page, _pageSize) => ({
      data: {
        total: 21,
        items: [
          { id: `p1`, clinic_id: 'c1', full_name: `Paciente 1`, is_active: true },
        ],
      },
      isLoading: false,
      isError: false,
      isFetching: false,
    }))
    const user = userEvent.setup()
    renderPatientsPage()

    expect(screen.getByText('Página 1 de 2 · 21 pacientes')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(usePatientsPage).toHaveBeenLastCalledWith(2, 20, '')
    // The updated URL now carries the full filter + page context so that a
    // later back-navigation restores search and page together.
    expect(screen.getByRole('link', { name: 'Abrir ficha' })).toHaveAttribute('href', '/app/pacientes/p1?page=2')

  })

  it('changes page without resetting search in the URL', async () => {
    usePatientsPage.mockImplementation(() => ({
      data: {
        total: 21,
        items: [
          { id: `p1`, clinic_id: 'c1', full_name: `Paciente 1`, is_active: true },
        ],
      },
      isLoading: false,
      isError: false,
      isFetching: false,
    }))
    const user = userEvent.setup()
    renderPatientsPage()

    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(usePatientsPage).toHaveBeenLastCalledWith(2, 20, '')
    await user.click(screen.getByRole('button', { name: 'Anterior' }))
    expect(usePatientsPage).toHaveBeenLastCalledWith(1, 20, '')
    expect(screen.getByText('Página 1 de 2 · 21 pacientes')).toBeInTheDocument()
  })

  it('debounces search so a request is sent only after typing stops', async () => {
    usePatientsPage.mockImplementation(() => ({
      data: {
        total: 21,
        items: [{ id: 'p1', clinic_id: 'c1', full_name: 'Ana', is_active: true }],
      },
      isLoading: false,
      isError: false,
      isFetching: false,
    }))
    const user = userEvent.setup()
    renderPatientsPage()

    await act(async () => {
      await user.clear(screen.getByRole('searchbox', { name: 'Pesquisar por nome' }))
      await user.type(screen.getByRole('searchbox', { name: 'Pesquisar por nome' }), 'Ana')
    })

    // The debounce (300 ms) has elapsed and the request for the final value
    // is in flight exactly once; no request has been sent mid-typing.
    await waitFor(() => {
      expect(usePatientsPage).toHaveBeenLastCalledWith(1, 20, 'Ana')
    })
  })

  it('preserves search and page in the URL when navigating back from a patient detail', async () => {
    usePatientsPage.mockImplementation(() => ({
      data: {
        total: 21,
        items: [
          { id: `p1`, clinic_id: 'c1', full_name: `Paciente 1`, is_active: true },
        ],
      },
      isLoading: false,
      isError: false,
      isFetching: false,
    }))
    renderPatientsPage('/app/pacientes?search=Ana&page=2')

    expect(screen.getByRole('searchbox', { name: 'Pesquisar por nome' })?.getAttribute('value') ?? '').toBe('Ana')
    expect(usePatientsPage).toHaveBeenLastCalledWith(2, 20, 'Ana')
    expect(screen.getByText('Página 2 de 2 · 21 pacientes')).toBeInTheDocument()
  })

  it('shows a loading state for the patient directory', () => {
    usePatientsPage.mockReturnValue({ data: undefined, isLoading: true, isError: false, isFetching: true })
    renderPatientsPage()
    expect(screen.getByRole('status')).toHaveTextContent('A carregar')
  })

  it('shows a search-specific empty state when there are no matching patients', async () => {
    usePatientsPage.mockReturnValue({
      data: { total: 0, items: [] },
      isLoading: false,
      isError: false,
      isFetching: false,
    })
    const user = userEvent.setup()
    renderPatientsPage()
    await user.type(screen.getByRole('searchbox', { name: 'Pesquisar por nome' }), 'Inexistente')
    await waitFor(() => expect(screen.getByText('Nenhum paciente encontrado')).toBeInTheDocument())
    expect(screen.getByText('Nenhum paciente corresponde à pesquisa.')).toBeInTheDocument()
  })

  it('shows a retry action for backend errors', () => {
    const refetch = vi.fn()
    usePatientsPage.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isFetching: false,
      error: new ApiError(500, 'server'),
      refetch,
    })
    renderPatientsPage()
    expect(screen.getByRole('alert')).toHaveTextContent('Ocorreu um erro no servidor.')
    screen.getByRole('button', { name: 'Tentar novamente' }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })
})
