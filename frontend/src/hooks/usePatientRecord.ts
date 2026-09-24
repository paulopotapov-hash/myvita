import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { patientsService } from '../services/patients'
import type { PatientUpdateRequest } from '../types/api'

export const patientQueryKey = (patientId: string | undefined) => ['patient', patientId] as const

export function usePatient(patientId: string | undefined) {
  return useQuery({
    queryKey: patientQueryKey(patientId),
    queryFn: ({ signal }) => patientsService.detail(patientId!, signal),
    enabled: Boolean(patientId),
    retry: false,
  })
}

export function useUpdatePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ patientId, payload }: { patientId: string; payload: PatientUpdateRequest }) =>
      patientsService.update(patientId, payload),
    onSuccess: async (_patient, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: patientQueryKey(variables.patientId) }),
        queryClient.invalidateQueries({ queryKey: ['patients'] }),
      ])
    },
  })
}
