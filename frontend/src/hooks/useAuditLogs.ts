import { useQuery } from '@tanstack/react-query'
import { auditLogsService, type AuditLogFilters } from '../services/auditLogs'

export function useAuditLogs(page: number, pageSize: number, filters: AuditLogFilters) {
  return useQuery({
    queryKey: ['audit-logs', page, pageSize, filters],
    queryFn: ({ signal }) => auditLogsService.list(page, pageSize, filters, signal),
  })
}
