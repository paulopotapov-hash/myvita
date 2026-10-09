import { expect, request, test } from '@playwright/test'
import { authState, loadSeed, PASSWORD } from './support'

const seed = loadSeed()

test.describe('route authorization (UX only; the backend decides)', () => {
  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    // Merged frontend (Parent B base): patients live under /patient; any staff area sends them home.
    for (const path of ['/app/pacientes', '/app/equipa', '/app/contas']) {
      test(`is sent back to the dashboard from ${path}`, async ({ page }) => {
        await page.goto(path)
        await expect(page).toHaveURL(/\/patient$/)
        await expect(page.getByRole('heading', { level: 1 })).toContainText(seed.names.patient.split(' ')[0])
      })
    }
  })

  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    for (const path of ['/app/equipa', '/app/contas', '/patient/saude']) {
      test(`is sent back to the dashboard from ${path}`, async ({ page }) => {
        await page.goto(path)
        await expect(page).toHaveURL(/\/app$/)
      })
    }
  })

  test.describe('as the clinic administrator', () => {
    test.use({ storageState: authState('clinic_admin') })

    test('is sent back to the dashboard from the patient-only health page', async ({ page }) => {
      await page.goto('/patient/saude')
      await expect(page).toHaveURL(/\/app$/)
    })

    test('can open the administration pages', async ({ page }) => {
      await page.goto('/app/equipa')
      await expect(page.getByRole('heading', { name: 'Equipa', level: 1 })).toBeVisible()
      await page.goto('/app/contas')
      await expect(page.getByRole('heading', { name: 'Contas', level: 1 })).toBeVisible()
    })
  })
})

test.describe('sessions', () => {
  test('an unauthenticated visitor cannot open any protected page', async ({ page }) => {
    for (const path of ['/app', '/app/consultas', '/app/pacientes', '/app/notificacoes', '/app/seguranca']) {
      await page.goto(path)
      await expect(page).toHaveURL(/\/login$/)
    }
  })

  test.describe('with an active session', () => {
    test.use({ storageState: authState('doctor') })

    test('is moved off the login page', async ({ page }) => {
      await page.goto('/login')
      await expect(page).toHaveURL(/\/app$/)
    })

    test('a vanished session (401) sends the user to login on the next request', async ({ page, context }) => {
      await page.goto('/app')
      await expect(page.getByRole('heading', { level: 1 })).toContainText(seed.names.doctor)

      await context.clearCookies()
      await page.getByRole('link', { name: 'Notificações' }).first().click()
      await expect(page).toHaveURL(/\/login$/)
      await expect(page.getByRole('heading', { name: 'Iniciar sessão' })).toBeVisible()
    })
  })

  test('a session revoked on the server is rejected by the app', async ({ browser, baseURL }) => {
    const api = await request.newContext({ baseURL })
    const email = `revoked.${Date.now()}@example.pt`
    const registered = await api.post('/api/v1/patients/register', {
      data: { clinic_id: seed.clinicId, full_name: 'Paciente Revogado E2E', email, password: PASSWORD },
    })
    expect(registered.ok()).toBe(true)
    const state = await api.storageState()
    const csrf = state.cookies.find((cookie) => cookie.name === 'myvita_csrf')?.value ?? ''

    const context = await browser.newContext({ storageState: state })
    const page = await context.newPage()
    await page.goto('/app')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Paciente Revogado E2E')

    const logout = await api.post('/api/v1/auth/logout', { headers: { 'X-CSRF-Token': csrf } })
    expect(logout.status()).toBe(204)

    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
    await context.close()
    await api.dispose()
  })
})
