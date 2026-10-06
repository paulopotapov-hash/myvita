import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { medicalRecordsService } from '../services/medicalRecords'
import { medicationsService } from '../services/medications'
import { notificationsService } from '../services/notifications'
import { clinicalDocumentsService } from '../services/clinicalDocuments'
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
export function useDeactivateMedication(patientId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: (id: string) => medicationsService.deactivate(id), onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'medications'] }) })
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

export function useClinicalDocuments(patientId: string, enabled = true) {
  return useQuery({
    queryKey: ['patients', patientId, 'documents'],
    queryFn: ({ signal }) => clinicalDocumentsService.listForPatient(patientId, signal),
    enabled: enabled && Boolean(patientId),
  })
}

export function useDocumentHistory(documentId: string) {
  return useQuery({
    queryKey: ['documents', documentId, 'versions'],
    queryFn: ({ signal }) => clinicalDocumentsService.history(documentId, signal),
    enabled: Boolean(documentId),
  })
}

export function useCreateDocumentNote(patientId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: { title: string; content: string }) => clinicalDocumentsService.createNote(patientId, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}

export function useUpdateDocumentNote(patientId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { title: string; content: string } }) => clinicalDocumentsService.updateNote(id, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}

export function useUploadClinicalDocument(patientId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ title, file }: { title: string; file: File }) => clinicalDocumentsService.uploadFile(patientId, title, file),
    onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}

export function useUploadDocumentVersion(patientId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, title, file }: { id: string; title: string; file: File }) => clinicalDocumentsService.uploadNewVersion(id, title, file),
    onSuccess: () => client.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}
