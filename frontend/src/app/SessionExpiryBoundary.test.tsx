import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { SESSION_EXPIRED_EVENT } from '../lib/apiClient'
import { SessionExpiryBoundary } from './SessionExpiryBoundary'

describe('SessionExpiryBoundary', () => {
  it('clears private cache and redirects an operational 401 to login', async () => {
    const client = new QueryClient()
    client.setQueryData(['patients'], [{ id: 'sensitive' }])
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/app/pacientes']}>
          <SessionExpiryBoundary />
          <Routes>
            <Route path="/app/pacientes" element={<div>Pacientes</div>} />
            <Route path="/login" element={<div>Login expirado</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { path: '/api/v1/patients' } }))
    expect(await screen.findByText('Login expirado')).toBeInTheDocument()
    expect(client.getQueryData(['patients'])).toBeUndefined()
  })
})
