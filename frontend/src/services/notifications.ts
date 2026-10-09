import { api } from '../lib/apiClient'
import type { NotificationPublic } from '../types/api'

export const notificationsService = {
  list: (page: number, pageSize: number, signal?: AbortSignal) => api.getPage<NotificationPublic>(`/api/v1/notifications?page=${page}&page_size=${pageSize}`, signal),
  markRead: (notificationId: string) => api.post<NotificationPublic>(`/api/v1/notifications/${notificationId}/read`),
  unreadCount: (signal?: AbortSignal) => api.get<{ count: number }>('/api/v1/notifications/unread-count', signal),
  markAllRead: () => api.post<{ updated_count: number }>('/api/v1/notifications/read-all'),
}
