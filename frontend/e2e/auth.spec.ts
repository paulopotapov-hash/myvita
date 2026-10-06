import { expect, request, test } from '@playwright/test'
import { loadSeed, loginThroughUi, PASSWORD } from './support'

const seed = loadSeed()

test.describe('login', () => {
  test('rejects invalid credentials without leaving the login page', async ({ page }) => {
    await page.goto('/login')
    await loginThroughUi(page, seed.emails.doctor, 'PalavraErrada123!')
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeEnabled()
  })

  test('validates the form before sending anything', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: 'Entrar' }).click()
    await expect(page.getByText('Introduz um email válido.')).toBeVisible()
    await expect(page.getByLabel('Email')).toHaveAttribute('aria-invalid', 'true')
    await expect(page.getByLabel('Email')).toBeFocused()
  })

  test('sends an unauthenticated visitor to login and back to the page they asked for', async ({ page }) => {
    await page.goto('/app/consultas')
    await expect(page).toHaveURL(/\/login$/)

    await loginThroughUi(page, seed.emails.doctor)
    await expect(page).toHaveURL(/\/app\/consultas$/)
    await expect(page.getByRole('heading', { name: 'Consultas', level: 1 })).toBeVisible()
    await expect(page.getByRole('banner').getByText(seed.names.doctor)).toBeVisible()

    await page.reload()
    await expect(page.getByRole('heading', { name: 'Consultas', level: 1 })).toBeVisible()
  })
})

test.describe('logout', () => {
  // Logout revokes every session of that user, so it uses its own account, never a shared fixture.
  test('ends the session and closes the protected area', async ({ page, baseURL }) => {
    const name = 'Paciente Logout E2E'
    const api = await request.newContext({ baseURL })
    const registered = await api.post('/api/v1/patients/register', {
      data: { clinic_id: seed.clinicId, full_name: name, email: `logout.${Date.now()}@example.pt`, password: PASSWORD },
    })
    expect(registered.ok()).toBe(true)
    await page.context().addCookies((await api.storageState()).cookies)
    await api.dispose()

    await page.goto('/app')
    await expect(page.getByRole('banner').getByText(name)).toBeVisible()

    await page.getByRole('button', { name: 'Sair' }).click()
    await expect(page).toHaveURL(/\/login$/)

    await page.goto('/app/notificacoes')
    await expect(page).toHaveURL(/\/login$/)
  })
})
