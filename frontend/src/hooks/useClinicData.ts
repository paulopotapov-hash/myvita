import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentsService } from '../services/appointments'
import type { AppointmentListFilters } from '../services/appointments'
import { clinicsService } from '../services/clinics'
import { patientsService } from '../services/patients'
import { staffService } from '../services/staff'
import type { AppointmentCreateRequest, AppointmentUpdateRequest, StaffCreateRequest } from '../types/api'

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
export function useAppointments(filters: AppointmentListFilters = {}) {
  return useQuery({
    queryKey: ['appointments', filters],
    queryFn: ({ signal }) => appointmentsService.list(filters, signal),
    staleTime: 60_000,
  })
}

/** The API accepts one status per request. Fetch the two active statuses in
 * parallel, then merge them so cancelled rows can never crowd real upcoming
 * appointments out of the dashboard's small result window. */
export function useUpcomingAppointments(startDate: string, limit = 5) {
  const scheduled = useAppointments({ start_date: startDate, status: 'scheduled', limit })
  const confirmed = useAppointments({ start_date: startDate, status: 'confirmed', limit })
  const ready = scheduled.data !== undefined && confirmed.data !== undefined
  const data = ready
    ? [...scheduled.data, ...confirmed.data]
        .sort((left, right) => left.scheduled_at.localeCompare(right.scheduled_at))
        .slice(0, limit)
    : undefined

  return {
    data,
    isLoading: scheduled.isLoading || confirmed.isLoading,
    error: scheduled.error ?? confirmed.error,
    refetch: () => Promise.all([scheduled.refetch(), confirmed.refetch()]),
  }
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

export function useAppointment(id: string | undefined) {
  return useQuery({
    queryKey: ['appointment', id],
    queryFn: ({ signal }) => appointmentsService.detail(id!, signal),
    enabled: Boolean(id),
  })
}

export function useUpdateAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AppointmentUpdateRequest }) =>
      appointmentsService.update(id, payload),
    onSuccess: (appointment) => {
      queryClient.setQueryData(['appointment', appointment.id], appointment)
      queryClient.invalidateQueries({ queryKey: ['appointments'] })
    },
  })
}

export function useCancelAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => appointmentsService.cancel(id),
    onSuccess: (appointment) => {
      queryClient.setQueryData(['appointment', appointment.id], appointment)
      queryClient.invalidateQueries({ queryKey: ['appointments'] })
    },
  })
}
