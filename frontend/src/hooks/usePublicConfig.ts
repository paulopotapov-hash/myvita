import { useQuery } from '@tanstack/react-query'
import { publicConfigService } from '../services/publicConfig'

export function usePublicConfig() {
  return useQuery({
    queryKey: ['public-config'],
    queryFn: ({ signal }) => publicConfigService.get(signal),
    staleTime: 5 * 60_000,
  })
}
