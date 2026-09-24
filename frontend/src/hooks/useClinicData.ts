import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentsService } from '../services/appointments'
import { clinicsService } from '../services/clinics'
import { patientsService } from '../services/patients'
import { staffService } from '../services/staff'
import type { AppointmentCreateRequest, AppointmentUpdateRequest, PatientUpdateRequest, StaffCreateRequest } from '../types/api'

/** Public clinic directory — used by the patient sign-up clinic picker.
 * No auth required, matches GET /api/v1/clinics being an open endpoint. */
export function useClinics() {
  return useQuery({
    queryKey: ['clinics'],
    queryFn: ({ signal }) => clinicsService.list(signal),
    staleTime: 5 * 60_000, // clinic directory changes rarely
  })
}

/** Own clinic's patient directory — the backend 403s this for the
 * `patient` role, so only call it from staff/admin pages. */
export function usePatients(enabled = true) {
  return useQuery({
    queryKey: ['patients'],
    queryFn: ({ signal }) => patientsService.list(signal),
    enabled,
  })
}

export function usePatientsPage(page: number, pageSize: number) {
  return useQuery({
    queryKey: ['patients', 'page', page, pageSize],
    queryFn: ({ signal }) => patientsService.listPage(page, pageSize, signal),
  })
}

export function usePatient(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId],
    queryFn: ({ signal }) => patientsService.detail(patientId, signal),
    enabled: Boolean(patientId),
  })
}

export function useUpdatePatient(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PatientUpdateRequest) => patientsService.update(patientId, payload),
    onSuccess: (patient) => {
      queryClient.setQueryData(['patients', patientId], patient)
      queryClient.invalidateQueries({ queryKey: ['patients'] })
    },
  })
}

/** Own clinic's staff directory — open to every authenticated role. */
export function useStaff() {
  return useQuery({
    queryKey: ['staff'],
    queryFn: ({ signal }) => staffService.list(signal),
  })
}

export function useCreateStaff() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: StaffCreateRequest) => staffService.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff'] })
    },
  })
}

/** Scoped entirely server-side (own record for patients, own clinic for
 * staff/admin) — see backend/app/modules/appointments/service.py. */
export function useAppointments() {
  return useQuery({
    queryKey: ['appointments'],
    queryFn: ({ signal }) => appointmentsService.list(signal),
  })
}

export function useCreateAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AppointmentCreateRequest) => appointmentsService.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appointments'] })
    },
  })
}

export function useUpdateAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AppointmentUpdateRequest }) =>
      appointmentsService.update(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['appointments'] }),
  })
}

export function useCancelAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => appointmentsService.cancel(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['appointments'] }),
  })
}
