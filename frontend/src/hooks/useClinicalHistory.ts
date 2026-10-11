import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clinicalHistoryService } from '../services/clinicalHistory'
import type { ClinicalHistoryCreateRequest, ClinicalHistoryUpdateRequest } from '../types/api'

const historyKey = (patientId: string) => ['patients', patientId, 'clinical-history'] as const

export function useClinicalHistory(patientId: string) {
  return useQuery({
    queryKey: historyKey(patientId),
    queryFn: ({ signal }) => clinicalHistoryService.list(patientId, signal),
    enabled: Boolean(patientId),
  })
}

export type HistoryAction =
  | { kind: 'create'; payload: ClinicalHistoryCreateRequest }
  | { kind: 'update'; id: string; payload: ClinicalHistoryUpdateRequest }
  | { kind: 'confirm'; id: string; version: number }
  | { kind: 'hide'; id: string; version: number; reason: string }
  | { kind: 'show'; id: string; version: number }
  | { kind: 'remove'; id: string; version: number; reason?: string }

/** Every change to the history; the list is refetched afterwards (versions change on each action). */
export function useClinicalHistoryAction(patientId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (action: HistoryAction) => {
      switch (action.kind) {
        case 'create':
          return clinicalHistoryService.create(patientId, action.payload)
        case 'update':
          return clinicalHistoryService.update(action.id, action.payload)
        case 'confirm':
          return clinicalHistoryService.confirm(action.id, action.version)
        case 'hide':
          return clinicalHistoryService.hide(action.id, action.version, action.reason)
        case 'show':
          return clinicalHistoryService.show(action.id, action.version)
        case 'remove':
          return clinicalHistoryService.remove(action.id, action.version, action.reason)
      }
    },
    onSettled: () => client.invalidateQueries({ queryKey: historyKey(patientId) }),
  })
}
