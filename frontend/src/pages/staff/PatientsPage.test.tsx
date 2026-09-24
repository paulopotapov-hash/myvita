import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { usePatients } from '../../hooks/useClinicData'
import { PatientsPage } from './PatientsPage'

vi.mock('../../hooks/useClinicData')

describe('PatientsPage record navigation', () => {
  it('links each patient to the correct individual record', async () => {
    vi.mocked(usePatients).mockReturnValue({
      data: [{ id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Martins', birth_date: null, phone: null }],
      isLoading: false, isError: false, error: null, refetch: vi.fn(),
    } as unknown as ReturnType<typeof usePatients>)
    render(
      <MemoryRouter initialEntries={['/app/pacientes']}>
        <Routes>
          <Route path="/app/pacientes" element={<PatientsPage />} />
          <Route path="/app/pacientes/:patientId" element={<div>Ficha individual</div>} />
        </Routes>
      </MemoryRouter>,
    )
    await userEvent.click(screen.getByRole('link', { name: 'Abrir ficha' }))
    expect(screen.getByText('Ficha individual')).toBeInTheDocument()
  })
})
