import { useMutation, useQueryClient } from '@tanstack/react-query'
import { authService } from '../services/auth'
import { clinicsService } from '../services/clinics'
import { patientsService } from '../services/patients'
import { SESSION_QUERY_KEY } from './useSession'
import type { ClinicOnboardingRequest, LoginRequest, PatientRegisterRequest } from '../types/api'
import { clearAuthenticatedState, publishAuthEvent } from '../lib/authSession'

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LoginRequest) => authService.login(payload),
    onSuccess: async () => {
      // The login response sets the cookie. Confirm the authoritative session
      // through /me instead of trusting a second, parallel identity source.
      await queryClient.fetchQuery({
        queryKey: SESSION_QUERY_KEY,
        queryFn: ({ signal }) => authService.me(signal),
        staleTime: 0,
      })
      publishAuthEvent('login')
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => authService.logout(),
    onSuccess: () => {
      clearAuthenticatedState(queryClient)
      publishAuthEvent('logout')
    },
  })
}

export function usePatientRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PatientRegisterRequest) => patientsService.register(payload),
    onSuccess: () => {
      // The backend auto-logs-in the new patient (sets the session cookie
      // in the same response) — refetch /me to pick that up.
      queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })
    },
  })
}

export function useClinicOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ClinicOnboardingRequest) => clinicsService.onboard(payload),
    onSuccess: () => {
      // Same as patient registration — onboarding auto-logs-in the new admin.
      queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY })
    },
  })
}
