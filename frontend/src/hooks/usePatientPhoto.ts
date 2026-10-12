import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { patientPhotosService } from '../services/patientPhotos'

const KEY = ['patient-photos'] as const

/** The signed-in patient's photo state (`enabled` false for staff sessions). */
export function useMyPhoto(enabled = true) {
  return useQuery({ queryKey: [...KEY, 'mine'], queryFn: ({ signal }) => patientPhotosService.mine(signal), enabled })
}

export function usePatientPhoto(patientId: string) {
  return useQuery({
    queryKey: [...KEY, 'patient', patientId],
    queryFn: ({ signal }) => patientPhotosService.forPatient(patientId, signal),
    enabled: Boolean(patientId),
    retry: false,
  })
}

function useRefresh() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: KEY })
}

export function useUploadPhoto() {
  const refresh = useRefresh()
  return useMutation({ mutationFn: (photo: Blob) => patientPhotosService.upload(photo), onSettled: refresh })
}

export function useRemovePhoto() {
  const refresh = useRefresh()
  return useMutation({ mutationFn: (photoId: string) => patientPhotosService.remove(photoId), onSettled: refresh })
}

export function usePhotoDecision() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (decision: { photoId: string; approve: true } | { photoId: string; approve: false; reason: string }) =>
      decision.approve ? patientPhotosService.approve(decision.photoId) : patientPhotosService.reject(decision.photoId, decision.reason),
    onSettled: refresh,
  })
}
