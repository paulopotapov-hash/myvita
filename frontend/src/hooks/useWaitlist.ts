import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { waitlistService } from '../services/waitlist'
import type { WaitlistScope } from '../types/scheduling'

const KEY = ['waitlist'] as const

export function useWaitlist() {
  return useQuery({ queryKey: KEY, queryFn: ({ signal }) => waitlistService.list(signal) })
}

function useRefresh() {
  const client = useQueryClient()
  return () => Promise.all([
    client.invalidateQueries({ queryKey: KEY }),
    client.invalidateQueries({ queryKey: ['appointments'] }),
    client.invalidateQueries({ queryKey: ['scheduling'] }),
  ])
}

export function useWaitlistChange() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (change: { kind: 'join'; appointmentId: string; scope: WaitlistScope } | { kind: 'leave'; entryId: string } | { kind: 'decline'; offerId: string }): Promise<unknown> => {
      if (change.kind === 'join') return waitlistService.join(change.appointmentId, change.scope)
      if (change.kind === 'leave') return waitlistService.leave(change.entryId)
      return waitlistService.decline(change.offerId)
    },
    onSettled: refresh,
  })
}

/** Take an offered earlier slot; resolves to the new appointment. */
export function useAcceptOffer() {
  const refresh = useRefresh()
  return useMutation({ mutationFn: (offerId: string) => waitlistService.accept(offerId), onSettled: refresh })
}
