import { api } from '../lib/apiClient'
import type { PublicConfig } from '../types/api'

export const publicConfigService = {
  get: (signal?: AbortSignal) => api.get<PublicConfig>('/api/v1/config/public', signal),
}
