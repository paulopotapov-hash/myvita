import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { PatientsPage } from './PatientsPage'

const { usePatientsPage } = vi.hoisted(() => ({ usePatientsPage: vi.fn() }))

vi.mock('../../hooks/useClinicData', () => ({ usePatientsPage }))

describe('PatientsPage', () => {
  it('uses backend totals to paginate the patient directory', async () => {
    usePatientsPage.mockImplementation((page: number) => ({
      data: {
        total: 21,
        items: [{ id: `p${page}`, clinic_id: 'c1', full_name: `Paciente ${page}`, birth_date: null, phone: null, national_health_number: null, is_active: true }],
      },
      isLoading: false,
      isError: false,
      isFetching: false,
    }))
    const user = userEvent.setup()
    render(<MemoryRouter><PatientsPage /></MemoryRouter>)

    expect(screen.getByText('Página 1 de 2 · 21 pacientes')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(usePatientsPage).toHaveBeenLastCalledWith(2, 20)
    expect(screen.getByRole('link', { name: 'Paciente 2' })).toHaveAttribute('href', '/app/pacientes/p2')
  })
})
