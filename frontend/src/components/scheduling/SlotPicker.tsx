import type { UseQueryResult } from '@tanstack/react-query'
import { clinicDateKey, formatClinicDay, formatClinicTime } from '../../lib/clinicTime'
import { toUserMessage } from '../../lib/errorMessages'
import type { Slot } from '../../types/scheduling'
import { Button } from '../Button'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { LoadingSpinner } from '../LoadingSpinner'

interface Props {
  slots: UseQueryResult<Slot[]>
  /** Show each slot's professional ("Qualquer disponível"). */
  showStaff: boolean
  onSelect: (slot: Slot) => void
  onMore?: () => void
}

/** Free slots from the server, as buttons grouped by day (Lisbon time). */
export function SlotPicker({ slots, showStaff, onSelect, onMore }: Props) {
  const byDay = new Map<string, Slot[]>()
  for (const item of slots.data ?? []) {
    const key = clinicDateKey(item.starts_at)
    byDay.set(key, [...(byDay.get(key) ?? []), item])
  }
  return (
    <>
      {slots.isLoading && <LoadingSpinner label="A procurar horários livres…" />}
      {slots.isError && <ErrorState message={toUserMessage(slots.error)} onRetry={() => slots.refetch()} />}
      {slots.data && slots.data.length === 0 && <EmptyState title="Sem horários livres nestes dias" />}
      <div className="flex flex-col gap-4">
        {[...byDay.entries()].map(([day, daySlots]) => (
          <div key={day}>
            <h3 className="mb-2 text-sm font-semibold text-slate-700 first-letter:uppercase">{formatClinicDay(daySlots[0].starts_at)}</h3>
            <ul className="flex flex-wrap gap-2">
              {daySlots.map((item) => (
                <li key={`${item.staff_id}-${item.starts_at}`}>
                  <button
                    type="button"
                    aria-label={`${formatClinicDay(item.starts_at)}, ${formatClinicTime(item.starts_at)}${showStaff ? `, ${item.staff_name}` : ''}`}
                    onClick={() => onSelect(item)}
                    className="flex min-h-11 min-w-20 flex-col items-center rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm font-medium text-teal-800 hover:bg-teal-50 focus-visible:outline-2 focus-visible:outline-teal-700"
                  >
                    {formatClinicTime(item.starts_at)}
                    {showStaff && <span className="text-xs font-normal text-slate-500">{item.staff_name}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {onMore && <Button variant="secondary" onClick={onMore}>Ver mais dias</Button>}
    </>
  )
}
