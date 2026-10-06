import { expect, test } from '@playwright/test'
import { authState, loadSeed } from './support'

const seed = loadSeed()

test.describe.serial('consent', () => {
  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('validates, grants and revokes a consent while keeping the history', async ({ page }) => {
      await page.goto('/app/saude')
      const section = page.getByRole('region', { name: 'Consentimentos' })

      await section.getByRole('button', { name: 'Conceder' }).click()
      await expect(section.getByText('Indica a finalidade do consentimento.')).toBeVisible()
      await expect(section.getByLabel('Finalidade')).toBeFocused()

      await section.getByLabel('Tipo').selectOption({ label: 'Investigação' })
      await section.getByLabel('Finalidade').fill('Estudo E2E')
      await section.getByRole('button', { name: 'Conceder' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Consentimento concedido' })).toBeVisible()

      const entry = section.getByRole('listitem').filter({ hasText: 'Estudo E2E' })
      await expect(entry).toContainText('Investigação')
      await expect(entry).toContainText('Concedido')

      // The same grant twice is a conflict reported by the backend.
      await section.getByLabel('Tipo').selectOption({ label: 'Investigação' })
      await section.getByLabel('Finalidade').fill('Estudo E2E')
      await section.getByRole('button', { name: 'Conceder' }).click()
      await expect(section.getByRole('alert').filter({ hasText: 'já concedido' })).toBeVisible()

      page.once('dialog', (confirm) => confirm.dismiss())
      await entry.getByRole('button', { name: 'Revogar' }).click()
      await expect(entry).toContainText('Concedido')

      page.once('dialog', (confirm) => confirm.accept())
      await entry.getByRole('button', { name: 'Revogar' }).click()
      await expect(section.getByRole('status').filter({ hasText: 'Consentimento revogado' })).toBeVisible()
      await expect(entry).toContainText('Revogado')
      await expect(entry.getByRole('button', { name: 'Revogar' })).toHaveCount(0)
    })
  })

  test.describe('as a doctor', () => {
    test.use({ storageState: authState('doctor') })

    test('reads the consent history but cannot change it', async ({ page }) => {
      await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
      const section = page.getByRole('region', { name: 'Consentimentos' })
      const entry = section.getByRole('listitem').filter({ hasText: 'Estudo E2E' })
      await expect(entry).toContainText('Revogado')
      await expect(section.getByRole('button')).toHaveCount(0)
      await expect(section.getByLabel('Finalidade')).toHaveCount(0)
    })
  })

  test.describe('as the clinic administrator', () => {
    test.use({ storageState: authState('clinic_admin') })

    test('is refused the patient file and never offered consents', async ({ page }) => {
      await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
      // The backend answers 403 for the patient record; the page shows that instead of any clinical content.
      await expect(page.getByRole('alert')).toBeVisible()
      await expect(page.getByRole('region', { name: 'Consentimentos' })).toHaveCount(0)
    })
  })
})
