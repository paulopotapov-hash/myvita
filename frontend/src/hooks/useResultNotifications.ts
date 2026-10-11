import { useCallback, useRef } from 'react'
import { useMarkNotificationRead, useNotifications } from './useClinicalData'

/** How many recent notifications are scanned (the backend's maximum page). */
export const NOTIFICATIONS_SCAN = 100

/**
 * Results the patient has not opened yet = unread "new result" notifications
 * (decision for the patient home). Returns the distinct result ids, newest first,
 * within the NOTIFICATIONS_SCAN most recent notifications (no aggregate endpoint).
 */
export function useUnopenedResultIds(enabled = true): string[] {
  const notifications = useNotifications(1, NOTIFICATIONS_SCAN, enabled)
  const ids: string[] = []
  for (const notification of notifications.data?.items ?? []) {
    const id = notification.result_target_id
    if (!notification.is_read && notification.target_type === 'result' && id && !ids.includes(id)) ids.push(id)
  }
  return ids
}

/**
 * Marks a result's unread notifications as read once the patient opens that
 * result, so "por abrir" reflects what they actually opened. Uses the existing
 * per-notification endpoint; each notification is attempted at most once.
 */
export function useMarkResultOpened(enabled: boolean): (resultId: string) => void {
  const notifications = useNotifications(1, NOTIFICATIONS_SCAN, enabled)
  const markRead = useMarkNotificationRead()
  const attempted = useRef(new Set<string>())
  const { mutate } = markRead
  const items = notifications.data?.items
  return useCallback(
    (resultId: string) => {
      for (const notification of items ?? []) {
        if (notification.is_read || notification.result_target_id !== resultId || attempted.current.has(notification.id)) continue
        attempted.current.add(notification.id)
        mutate(notification.id)
      }
    },
    [items, mutate],
  )
}
