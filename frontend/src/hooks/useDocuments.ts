import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { documentsService } from '../services/documents'

export function usePatientDocuments(patientId: string, page: number, pageSize: number) {
  return useQuery({
    queryKey: ['patients', patientId, 'documents', page, pageSize],
    queryFn: ({ signal }) => documentsService.listForPatient(patientId, page, pageSize, signal),
    enabled: Boolean(patientId),
  })
}

export function useUploadDocument(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => documentsService.upload(patientId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}

export function useDeleteDocument(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) => documentsService.remove(documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}

export function useDownloadDocument() {
  return useMutation({
    mutationFn: async ({ documentId, fallbackName }: { documentId: string; fallbackName: string }) => {
      const { blob, filename } = await documentsService.download(documentId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename ?? fallbackName
      anchor.rel = 'noopener'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    },
  })
}
