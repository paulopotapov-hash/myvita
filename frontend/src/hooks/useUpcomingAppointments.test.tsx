import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { appointmentsService } from '../services/appointments'
import type { AppointmentPublic } from '../types/api'
import { useUpcomingAppointments } from './useClinicData'

vi.mock('../services/appointments')

function item(id: string, scheduledAt: string, status: AppointmentPublic['status']): AppointmentPublic {
  return {
    id,
    clinic_id: 'clinic-1',
    patient_id: 'patient-1',
    staff_id: 'staff-1',
    scheduled_at: scheduledAt,
    duration_minutes: 30,
    status,
    reason: null,
  }
}

describe('useUpcomingAppointments', () => {
  it('requests only active statuses, merges chronologically and respects the limit', async () => {
    vi.mocked(appointmentsService.list).mockImplementation(async (filters) => {
      if (filters?.status === 'scheduled') {
        return [
          item('later', '2030-05-03T09:00:00Z', 'scheduled'),
          item('first', '2030-05-01T09:00:00Z', 'scheduled'),
        ]
      }
      return [item('middle', '2030-05-02T09:00:00Z', 'confirmed')]
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useUpcomingAppointments('2030-05-01T00:00:00Z', 2), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    })

    await waitFor(() => expect(result.current.data).toHaveLength(2))
    expect(result.current.data?.map((appointment) => appointment.id)).toEqual(['first', 'middle'])
    expect(vi.mocked(appointmentsService.list).mock.calls.map(([filters]) => filters?.status).sort()).toEqual([
      'confirmed',
      'scheduled',
    ])
    expect(vi.mocked(appointmentsService.list).mock.calls.every(([filters]) => filters?.limit === 2)).toBe(true)
  })
})
