import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { schedulingService } from '../services/scheduling'
import type { AbsenceKind, AppointmentTypeOption, BookingMode, BookingRequest, BookingSettings, ScheduleRule, Specialty } from '../types/scheduling'

const KEY = ['scheduling'] as const

export function useSpecialties() {
  return useQuery({ queryKey: [...KEY, 'specialties'], queryFn: ({ signal }) => schedulingService.specialties(signal) })
}
export function useAppointmentTypes() {
  return useQuery({ queryKey: [...KEY, 'types'], queryFn: ({ signal }) => schedulingService.types(signal) })
}
export function useBookingSettings() {
  return useQuery({ queryKey: [...KEY, 'settings'], queryFn: ({ signal }) => schedulingService.settings(signal) })
}
export function useProfessionals(enabled = true) {
  return useQuery({ queryKey: [...KEY, 'professionals'], queryFn: ({ signal }) => schedulingService.professionals(signal), enabled })
}
export function useSchedule(staffId: string) {
  return useQuery({
    queryKey: [...KEY, 'schedule', staffId],
    queryFn: ({ signal }) => schedulingService.schedule(staffId, signal),
    enabled: Boolean(staffId),
  })
}
export function useAgenda(from: string, to: string, staffId?: string) {
  return useQuery({
    queryKey: [...KEY, 'agenda', from, to, staffId ?? 'own'],
    queryFn: ({ signal }) => schedulingService.agenda(from, to, staffId, signal),
  })
}
export function useSlots(typeId: string, from: string, to: string, staffId?: string) {
  return useQuery({
    queryKey: [...KEY, 'slots', typeId, from, to, staffId ?? 'any'],
    queryFn: ({ signal }) => schedulingService.slots(typeId, from, to, staffId, signal),
    enabled: Boolean(typeId && from && to),
  })
}

export function useBookableProfessionals(typeId: string) {
  return useQuery({
    queryKey: [...KEY, 'bookable', typeId],
    queryFn: ({ signal }) => schedulingService.bookableProfessionals(typeId, signal),
    enabled: Boolean(typeId),
  })
}

/** The patient's booking: on success the appointment lists and the slots are refreshed. */
export function useBook() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: BookingRequest) => schedulingService.book(payload),
    onSettled: () => Promise.all([
      client.invalidateQueries({ queryKey: KEY }),
      client.invalidateQueries({ queryKey: ['appointments'] }),
    ]),
  })
}

export function useRescheduleSlots(appointmentId: string, from: string, to: string, professional: 'same' | 'any', enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'reschedule-slots', appointmentId, from, to, professional],
    queryFn: ({ signal }) => schedulingService.rescheduleSlots(appointmentId, from, to, professional, signal),
    enabled: enabled && Boolean(appointmentId && from && to),
  })
}

function useRefreshAppointments() {
  const client = useQueryClient()
  return () => Promise.all([
    client.invalidateQueries({ queryKey: KEY }),
    client.invalidateQueries({ queryKey: ['appointments'] }),
    client.invalidateQueries({ queryKey: ['appointment-requests'] }),
  ])
}

/** The patient cancels their own appointment (the server applies the clinic's deadline). */
export function useCancelBooking() {
  const refresh = useRefreshAppointments()
  return useMutation({ mutationFn: (appointmentId: string) => schedulingService.cancelBooking(appointmentId), onSettled: refresh })
}

/** The patient moves their own appointment to a free slot; resolves to the new appointment. */
export function useReschedule() {
  const refresh = useRefreshAppointments()
  return useMutation({
    mutationFn: ({ appointmentId, ...payload }: { appointmentId: string; starts_at: string; staff_id?: string }) =>
      schedulingService.reschedule(appointmentId, payload),
    onSettled: refresh,
  })
}

export type SchedulingChange =
  | { kind: 'createSpecialty'; name: string }
  | { kind: 'updateSpecialty'; id: string; payload: Partial<Pick<Specialty, 'name' | 'active'>> }
  | { kind: 'createType'; payload: { name: string; duration_minutes: number; specialty_id: string; booking_mode: BookingMode } }
  | { kind: 'updateType'; id: string; payload: Partial<Omit<AppointmentTypeOption, 'id'>> }
  | { kind: 'settings'; payload: BookingSettings }
  | { kind: 'professional'; id: string; payload: { specialty_id?: string | null; accepts_new_patients?: boolean } }
  | { kind: 'schedule'; staffId: string; rules: ScheduleRule[] }
  | { kind: 'addAbsence'; payload: { starts_at: string; ends_at: string; kind: AbsenceKind }; staffId?: string }
  | { kind: 'deleteAbsence'; id: string }

/** Every scheduling configuration change; the whole scheduling cache is refreshed afterwards. */
export function useSchedulingChange() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (change: SchedulingChange): Promise<unknown> => {
      switch (change.kind) {
        case 'createSpecialty':
          return schedulingService.createSpecialty(change.name)
        case 'updateSpecialty':
          return schedulingService.updateSpecialty(change.id, change.payload)
        case 'createType':
          return schedulingService.createType(change.payload)
        case 'updateType':
          return schedulingService.updateType(change.id, change.payload)
        case 'settings':
          return schedulingService.updateSettings(change.payload)
        case 'professional':
          return schedulingService.updateProfessional(change.id, change.payload)
        case 'schedule':
          return schedulingService.replaceSchedule(change.staffId, change.rules)
        case 'addAbsence':
          return schedulingService.addAbsence(change.payload, change.staffId)
        case 'deleteAbsence':
          return schedulingService.deleteAbsence(change.id)
      }
    },
    onSettled: () => client.invalidateQueries({ queryKey: KEY }),
  })
}
