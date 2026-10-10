import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clinicalResultsService } from '../services/clinicalResults'
import type { ClinicalResultCorrectionRequest, ClinicalResultCreateRequest, ClinicalResultUpdateRequest } from '../types/api'

const resultsKey = (patientId: string) => ['patients', patientId, 'results'] as const

export function useClinicalResults(patientId: string, page: number, pageSize: number) {
  return useQuery({
    queryKey: [...resultsKey(patientId), page, pageSize],
    queryFn: ({ signal }) => clinicalResultsService.list(patientId, page, pageSize, undefined, signal),
    enabled: Boolean(patientId),
  })
}

/** A single result, e.g. opened from a notification deep link that is not on the current page. */
export function useClinicalResult(resultId: string | null) {
  return useQuery({
    queryKey: ['results', resultId],
    queryFn: ({ signal }) => clinicalResultsService.detail(resultId ?? '', signal),
    enabled: Boolean(resultId),
    retry: false,
  })
}

function useInvalidateResults(patientId: string) {
  const client = useQueryClient()
  return () => Promise.all([
    client.invalidateQueries({ queryKey: resultsKey(patientId) }),
    client.invalidateQueries({ queryKey: ['results'] }),
  ])
}

export function useCreateClinicalResult(patientId: string) {
  const invalidate = useInvalidateResults(patientId)
  return useMutation({
    mutationFn: (payload: ClinicalResultCreateRequest) => clinicalResultsService.create(patientId, payload),
    onSuccess: invalidate,
  })
}

export function useUpdateClinicalResult(patientId: string) {
  const invalidate = useInvalidateResults(patientId)
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ClinicalResultUpdateRequest }) => clinicalResultsService.update(id, payload),
    onSuccess: invalidate,
  })
}

export function useReleaseClinicalResult(patientId: string) {
  const invalidate = useInvalidateResults(patientId)
  return useMutation({
    mutationFn: (resultId: string) => clinicalResultsService.release(resultId),
    onSuccess: invalidate,
  })
}

export function useCorrectClinicalResult(patientId: string) {
  const invalidate = useInvalidateResults(patientId)
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ClinicalResultCorrectionRequest }) => clinicalResultsService.correct(id, payload),
    onSuccess: invalidate,
  })
}
