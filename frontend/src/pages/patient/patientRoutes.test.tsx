import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

// Opens every patient URL through the real routes and layout (only the network
// is stubbed) and checks that the page shown always matches the URL, both on a
// direct visit and after navigating in the app.

const PATIENT = {
  id: 'u1', email: 'ana@example.pt', full_name: 'Ana Silva', role: 'patient',
  clinic_id: 'c1', staff_role: null, patient_id: 'p1',
}

function json(body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json', ...headers } })
}

function stubApi() {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const { pathname } = new URL(String(input), 'http://localhost')
    if (pathname === '/api/v1/auth/me') return json(PATIENT)
    if (pathname === '/api/v1/patients/p1') {
      return json({ id: 'p1', clinic_id: 'c1', full_name: 'Ana Silva', birth_date: '1990-01-02', phone: '912345678', address: { street: null, postal_code: null, locality: null }, identifiers: { nif: '••••••789', niss: null, national_health_number: null }, is_active: true })
    }
    if (pathname === '/api/v1/clinics/c1') return json({ id: 'c1', name: 'Clínica Centro' })
    if (pathname === '/api/v1/patients/p1/identification') {
      return json({ id: 'p1', full_name: 'Ana Silva', identifiers: { nif: '••••••789', niss: null, national_health_number: null }, can_edit: false })
    }
    if (pathname.endsWith('/unread-count')) return json({ count: 0 })
    if (pathname.startsWith('/api/v1/medical-records/')) return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404, headers: { 'Content-Type': 'application/json' } })
    // Every list endpoint: empty.
    return json([], { 'X-Total-Count': '0' })
  }))
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

function renderAt(path: string) {
  stubApi()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('patient area: one page per section', () => {
  it.each([
    ['/patient/consultas', 'As minhas consultas', 'As minhas consultas · myVita'],
    ['/patient/resultados', 'Os meus resultados', 'Os meus resultados · myVita'],
    ['/patient/medicacao', 'A minha medicação', 'A minha medicação · myVita'],
    ['/patient/documentos', 'Os meus documentos', 'Os meus documentos · myVita'],
    ['/patient/saude', 'Resumo de saúde', 'Resumo de saúde · myVita'],
    ['/patient/consentimentos', 'Os meus consentimentos', 'Os meus consentimentos · myVita'],
    ['/patient/perfil', 'O meu perfil', 'Perfil · myVita'],
  ])('opening %s directly shows "%s"', async (path, title, documentTitle) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    // The tabbed patient file is staff-only.
    expect(screen.queryByRole('tablist', { name: 'Secções da ficha' })).not.toBeInTheDocument()
    expect(screen.queryByText('Ficha do paciente')).not.toBeInTheDocument()
    await waitFor(() => expect(document.title).toBe(documentTitle))
  })

  it('keeps the page in sync with the URL when navigating between sections (Consentimentos → Resultados → Medicação)', async () => {
    const user = userEvent.setup()
    renderAt('/patient/consentimentos')
    expect(await screen.findByRole('heading', { level: 1, name: 'Os meus consentimentos' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Menu de navegação' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Menu' })).getByRole('link', { name: 'Resultados' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/resultados')
    expect(await screen.findByRole('heading', { level: 1, name: 'Os meus resultados' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Os meus consentimentos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Consentimentos' })).not.toBeInTheDocument()
    await waitFor(() => expect(document.title).toBe('Os meus resultados · myVita'))

    await user.click(screen.getByRole('button', { name: 'Menu de navegação' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Menu' })).getByRole('link', { name: 'Medicação' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'A minha medicação' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Os meus resultados' })).not.toBeInTheDocument()
  })

  it('redirects the old /patient/registos link to the health summary, keeping the linked record', async () => {
    renderAt('/patient/registos?record=rec-9')
    expect(await screen.findByRole('heading', { level: 1, name: 'Resumo de saúde' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/saude?record=rec-9')
    expect(await screen.findByText(/Este registo não está disponível/)).toBeInTheDocument()
  })
})
