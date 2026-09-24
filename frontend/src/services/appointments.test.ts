import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/apiClient'
import { appointmentsService } from './appointments'

vi.mock('../lib/apiClient', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

beforeEach(() => vi.clearAllMocks())

describe('appointmentsService', () => {
  it('serializes the backend-supported list filters', () => {
    appointmentsService.list({
      limit: 20,
      offset: 40,
      patient_id: 'patient-1',
      staff_id: 'staff-1',
      status: 'confirmed',
      start_date: '2030-05-01T00:00:00.000Z',
      end_date: '2030-05-31T23:59:59.999Z',
    })

    const path = vi.mocked(api.get).mock.calls[0][0]
    const url = new URL(path, 'https://myvita.test')
    expect(url.pathname).toBe('/api/v1/appointments')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      limit: '20',
      offset: '40',
      patient_id: 'patient-1',
      staff_id: 'staff-1',
      status: 'confirmed',
      start_date: '2030-05-01T00:00:00.000Z',
      end_date: '2030-05-31T23:59:59.999Z',
    })
  })

  it('uses the real detail, update and cancellation contracts', () => {
    appointmentsService.detail('appointment-1')
    appointmentsService.update('appointment-1', { status: 'confirmed' })
    appointmentsService.cancel('appointment-1')

    expect(api.get).toHaveBeenCalledWith('/api/v1/appointments/appointment-1', undefined)
    expect(api.patch).toHaveBeenCalledWith('/api/v1/appointments/appointment-1', { status: 'confirmed' })
    expect(api.post).toHaveBeenCalledWith('/api/v1/appointments/appointment-1/cancel')
  })
})
