import { expect, test } from '@playwright/test'
import { authState, loadSeed } from './support'

const seed = loadSeed()

test.describe.serial('consent', () => {
  test.describe('as the patient', () => {
    test.use({ storageState: authState('patient') })

    test('validates, grants and revokes a consent while keeping the history', async ({ page }) => {
      // The patient's consents have their own page (one page per section).
      await page.goto('/patient/consentimentos')
      await expect(page.getByRole('heading', { level: 1, name: 'Os meus consentimentos' })).toBeVisible()
      const section = page.getByRole('main')

      await section.getByRole('button', { name: 'Conceder' }).click()
      await expect(section.getByText('Indica a finalidade do consentimento.')).toBeVisible()
      // Accessibility requirement kept from Parent A: focus moves to the first invalid field.
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
      await page.getByRole('tab', { name: 'Consentimentos' }).click()
      const section = page.getByRole('tabpanel', { name: 'Consentimentos' })
      const entry = section.getByRole('listitem').filter({ hasText: 'Estudo E2E' })
      await expect(entry).toContainText('Revogado')
      await expect(section.getByRole('button')).toHaveCount(0)
      await expect(section.getByLabel('Finalidade')).toHaveCount(0)
    })
  })

  test.describe('as the clinic administrator', () => {
    test.use({ storageState: authState('clinic_admin') })

    test('gets only the patient identification and is never offered consents', async ({ page }) => {
      await page.goto(`/app/pacientes/${seed.patientIds.patient}`)
      // Administrative roles see the name and identifiers only; consents stay with the care team.
      await expect(page.getByRole('region', { name: 'Dados identificativos' })).toBeVisible()
      await expect(page.getByRole('tab', { name: 'Consentimentos' })).toHaveCount(0)
      await expect(page.getByRole('tabpanel', { name: 'Consentimentos' })).toHaveCount(0)
    })
  })
})
