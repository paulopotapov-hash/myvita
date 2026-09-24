import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { NetworkError } from '../../lib/apiClient'
import type { AppointmentPublic, AppointmentStatus } from '../../types/api'
import { DashboardAppointments } from './DashboardAppointments'

const statuses: AppointmentStatus[] = ['scheduled', 'confirmed', 'completed', 'cancelled', 'no_show']

function items(): AppointmentPublic[] {
  return statuses.map((status, index) => ({
    id: String(index),
    clinic_id: 'clinic-1',
    patient_id: 'patient-1',
    staff_id: 'staff-1',
    scheduled_at: new Date(Date.now() + (index + 1) * 3_600_000).toISOString(),
    duration_minutes: 30,
    status,
    reason: null,
  }))
}

function renderSection(props: Partial<React.ComponentProps<typeof DashboardAppointments>> = {}) {
  const defaults: React.ComponentProps<typeof DashboardAppointments> = {
    title: 'Consultas',
    appointments: items(),
    isLoading: false,
    error: null,
    onRetry: vi.fn(),
    emptyTitle: 'Sem consultas',
    emptyDescription: 'Não existem consultas.',
  }
  return render(
    <MemoryRouter>
      <DashboardAppointments {...defaults} {...props} />
    </MemoryRouter>,
  )
}

describe('DashboardAppointments', () => {
  it('renders every supported appointment status as text, not color alone', () => {
    renderSection()
    for (const label of ['Agendada', 'Confirmada', 'Concluída', 'Cancelada', 'Faltou']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('shows a safe API error and retries on request', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    renderSection({ appointments: undefined, error: new NetworkError(), onRetry })

    expect(screen.getByRole('alert')).toHaveTextContent('Sem ligação ao servidor')
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
