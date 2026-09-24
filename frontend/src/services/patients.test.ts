import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/apiClient'
import { patientsService } from './patients'

vi.mock('../lib/apiClient', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

beforeEach(() => vi.clearAllMocks())

describe('patientsService', () => {
  it('uses the B2 detail and update endpoints', () => {
    const payload = { full_name: 'Ana Martins', phone: '910000000' }
    patientsService.detail('patient-1')
    patientsService.update('patient-1', payload)

    expect(api.get).toHaveBeenCalledWith('/api/v1/patients/patient-1', undefined)
    expect(api.patch).toHaveBeenCalledWith('/api/v1/patients/patient-1', payload)
  })
})
