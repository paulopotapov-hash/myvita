import { api } from '../lib/apiClient'
import type { AuditLogPublic } from '../types/api'

export interface AuditLogFilters {
  action?: string
  actorUserId?: string
  resourceType?: string
  resourceId?: string
  dateFrom?: string
  dateTo?: string
}

export function auditLogQuery(page: number, pageSize: number, filters: AuditLogFilters): string {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (filters.action) params.set('action', filters.action)
  if (filters.actorUserId) params.set('actor_user_id', filters.actorUserId)
  if (filters.resourceType) params.set('resource_type', filters.resourceType)
  if (filters.resourceId) params.set('resource_id', filters.resourceId)
  if (filters.dateFrom) params.set('date_from', new Date(filters.dateFrom).toISOString())
  if (filters.dateTo) params.set('date_to', new Date(filters.dateTo).toISOString())
  return params.toString()
}

export const auditLogsService = {
  list: (page: number, pageSize: number, filters: AuditLogFilters, signal?: AbortSignal) =>
    api.getPage<AuditLogPublic>(`/api/v1/audit-logs?${auditLogQuery(page, pageSize, filters)}`, signal),
}
