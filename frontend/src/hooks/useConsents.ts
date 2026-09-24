import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consentsService } from '../services/consents'
import type { ConsentCreateRequest } from '../types/api'

export function usePatientConsents(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'consents'],
    queryFn: ({ signal }) => consentsService.listForPatient(patientId, signal),
    enabled: Boolean(patientId),
  })
}

export function useGrantConsent(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConsentCreateRequest) => consentsService.grant(patientId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'consents'] }),
  })
}

export function useRevokeConsent(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (consentId: string) => consentsService.revoke(consentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'consents'] }),
  })
}
