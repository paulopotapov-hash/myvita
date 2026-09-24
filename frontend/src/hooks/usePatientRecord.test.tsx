import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { patientsService } from '../services/patients'
import type { PatientPublic } from '../types/api'
import { patientQueryKey, usePatient, useUpdatePatient } from './usePatientRecord'

vi.mock('../services/patients')

const patient: PatientPublic = {
  id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Martins', birth_date: null, phone: null,
  national_health_number: null, is_active: true, created_at: '2030-01-01T00:00:00Z', updated_at: '2030-01-01T00:00:00Z',
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}

describe('patient record hooks', () => {
  it('loads the requested patient under a stable patient-specific query key', async () => {
    vi.mocked(patientsService.detail).mockResolvedValue(patient)
    const { wrapper } = setup()
    const { result } = renderHook(() => usePatient('patient-1'), { wrapper })
    await waitFor(() => expect(result.current.data).toEqual(patient))
    expect(patientsService.detail).toHaveBeenCalledWith('patient-1', expect.any(AbortSignal))
    expect(patientQueryKey('patient-1')).toEqual(['patient', 'patient-1'])
  })

  it('invalidates the detail and patient list after the server confirms an update', async () => {
    vi.mocked(patientsService.update).mockResolvedValue({ ...patient, full_name: 'Ana Silva' })
    const { client, wrapper } = setup()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useUpdatePatient(), { wrapper })
    act(() => result.current.mutate({ patientId: 'patient-1', payload: { full_name: 'Ana Silva' } }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['patient', 'patient-1'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['patients'] })
  })
})
