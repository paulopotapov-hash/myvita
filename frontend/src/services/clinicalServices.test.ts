import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/apiClient'
import { medicalRecordsService } from './medicalRecords'
import { medicationsService } from './medications'

vi.mock('../lib/apiClient', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

describe('clinical API services', () => {
  beforeEach(() => vi.clearAllMocks())

  it('maps medical-record list, detail, creation, update and revisions to B6', () => {
    const payload = { title: 'Avaliação', content: 'Evolução clínica' }
    medicalRecordsService.list('patient-1')
    medicalRecordsService.detail('record-1')
    medicalRecordsService.create('patient-1', payload)
    medicalRecordsService.update('record-1', payload)
    medicalRecordsService.revisions('record-1')

    expect(api.get).toHaveBeenNthCalledWith(1, '/api/v1/patients/patient-1/medical-records', undefined)
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/v1/medical-records/record-1', undefined)
    expect(api.post).toHaveBeenCalledWith('/api/v1/patients/patient-1/medical-records', payload)
    expect(api.patch).toHaveBeenCalledWith('/api/v1/medical-records/record-1', payload)
    expect(api.get).toHaveBeenNthCalledWith(3, '/api/v1/medical-records/record-1/revisions', undefined)
  })

  it('maps medication list, detail, creation and lifecycle updates to B6', () => {
    const createPayload = { name: 'Amoxicilina', dosage: '500 mg', start_date: '2026-09-24' }
    medicationsService.list('patient-1')
    medicationsService.detail('medication-1')
    medicationsService.create('patient-1', createPayload)
    medicationsService.update('medication-1', { status: 'discontinued' })

    expect(api.get).toHaveBeenNthCalledWith(1, '/api/v1/patients/patient-1/medications', undefined)
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/v1/medications/medication-1', undefined)
    expect(api.post).toHaveBeenCalledWith('/api/v1/patients/patient-1/medications', createPayload)
    expect(api.patch).toHaveBeenCalledWith('/api/v1/medications/medication-1', { status: 'discontinued' })
  })
})
