import { expect, test } from '@playwright/test'
import { authState, loadSeed, loginThroughUi } from './support'

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
  test.use({ storageState: authState('other_patient') })

  test('ends the session and closes the protected area', async ({ page }) => {
    await page.goto('/app')
    await expect(page.getByRole('banner').getByText(seed.names.other_patient)).toBeVisible()

    await page.getByRole('button', { name: 'Sair' }).click()
    await expect(page).toHaveURL(/\/login$/)

    await page.goto('/app/notificacoes')
    await expect(page).toHaveURL(/\/login$/)
  })
})
