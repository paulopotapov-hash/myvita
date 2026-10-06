import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { medicalRecordsService } from '../services/medicalRecords'
import { medicationsService } from '../services/medications'
import { notificationsService } from '../services/notifications'
import type { MedicalRecordWriteRequest, MedicationCreateRequest, MedicationUpdateRequest } from '../types/api'

export function useMedicalRecords(patientId: string, enabled = true) {
  return useQuery({ queryKey: ['patients', patientId, 'medical-records'], queryFn: ({ signal }) => medicalRecordsService.list(patientId, signal), enabled: enabled && Boolean(patientId) })
}
export function useMedicalRecordRevisions(recordId: string) {
  return useQuery({ queryKey: ['medical-records', recordId, 'revisions'], queryFn: ({ signal }) => medicalRecordsService.revisions(recordId, signal), enabled: Boolean(recordId) })
}
export function useCreateMedicalRecord(patientId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: (payload: MedicalRecordWriteRequest) => medicalRecordsService.create(patientId, payload), onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'medical-records'] }) })
}
export function useUpdateMedicalRecord(patientId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: MedicalRecordWriteRequest }) => medicalRecordsService.update(id, payload), onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'medical-records'] }) })
}
export function useMedications(patientId: string, enabled = true) {
  return useQuery({ queryKey: ['patients', patientId, 'medications'], queryFn: ({ signal }) => medicationsService.list(patientId, signal), enabled: enabled && Boolean(patientId) })
}
export function useCreateMedication(patientId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: (payload: MedicationCreateRequest) => medicationsService.create(patientId, payload), onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'medications'] }) })
}
export function useUpdateMedication(patientId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: MedicationUpdateRequest }) => medicationsService.update(id, payload), onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'medications'] }) })
}
export function useNotifications(page: number, pageSize: number) {
  return useQuery({ queryKey: ['notifications', page, pageSize], queryFn: ({ signal }) => notificationsService.list(page, pageSize, signal) })
}
export function useMarkNotificationRead() {
  const client = useQueryClient()
  return useMutation({ mutationFn: (id: string) => notificationsService.markRead(id), onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }) })
}
