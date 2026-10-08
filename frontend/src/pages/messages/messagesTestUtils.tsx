import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import type { ConversationPublic, MessagePublic } from '../../types/api'

export type Handler = (url: URL, init: RequestInit | undefined) => Response | Promise<Response> | undefined

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

/** Routes fetch() to handlers; unmatched requests fail loudly. Returns the call log. */
export function mockFetch(handler: Handler) {
  const calls: { method: string; path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      calls.push({
        method: init?.method ?? 'GET',
        path: url.pathname + url.search,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      })
      const response = await handler(url, init)
      if (!response) throw new Error(`Unhandled request ${init?.method ?? 'GET'} ${url.pathname}${url.search}`)
      return response
    }),
  )
  return calls
}

export function renderAt(path: string, routes: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>{routes}</Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export const PATIENT_USER = {
  id: 'user-patient',
  email: 'p@example.pt',
  full_name: 'Ana Paciente',
  role: 'patient' as const,
  clinic_id: 'clinic-1',
  staff_role: null,
  patient_id: 'patient-1',
}

export const DOCTOR_USER = {
  id: 'user-doctor',
  email: 'd@example.pt',
  full_name: 'Dr. Rui',
  role: 'staff' as const,
  clinic_id: 'clinic-1',
  staff_role: 'doctor' as const,
  patient_id: null,
}

export function conversation(overrides: Partial<ConversationPublic> = {}): ConversationPublic {
  return {
    id: 'conv-1',
    clinic_id: 'clinic-1',
    patient_id: 'patient-1',
    staff_id: 'staff-1',
    patient_name: 'Ana Paciente',
    staff_name: 'Dr. Rui',
    unread_count: 0,
    created_at: '2026-10-01T09:00:00Z',
    updated_at: '2026-10-02T09:00:00Z',
    ...overrides,
  }
}

export function message(overrides: Partial<MessagePublic> = {}): MessagePublic {
  return {
    id: 'msg-1',
    conversation_id: 'conv-1',
    sender_user_id: 'user-doctor',
    body: 'Olá',
    read_at: null,
    created_at: '2026-10-02T09:00:00Z',
    ...overrides,
  }
}
